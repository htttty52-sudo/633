import random
import logging
from datetime import datetime

import redis as redis_lib
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device
from app.ota_models import OtaDeviceTask
from app.idempotency import acquire_processing_lock, mark_processed, is_already_processed
from app.config import OTA_UPGRADE_SUCCESS_RATE

logger = logging.getLogger(__name__)

OTA_FAILURE_MESSAGES = [
    "Firmware download timeout: device unreachable",
    "Flash write error: insufficient storage space",
    "Firmware checksum verification failed",
    "Bootloader update failed: partition table mismatch",
    "Device rebooted unexpectedly during upgrade",
    "Firmware signature verification failed",
    "Network interruption during file transfer",
    "Watchdog timer expired during upgrade process",
]


def process_message(db: Session, r: redis_lib.Redis, fields: dict, worker_name: str):
    idempotency_key = fields["idempotency_key"]
    ota_device_task_id = int(fields["ota_device_task_id"])

    if is_already_processed(r, idempotency_key):
        logger.info(f"[{worker_name}] SKIP duplicate {idempotency_key}")
        return

    if not acquire_processing_lock(r, idempotency_key, ttl=120):
        logger.info(f"[{worker_name}] SKIP locked {idempotency_key}")
        return

    logger.info(f"[{worker_name}] Processing {idempotency_key} for device_task {ota_device_task_id}")

    device_task = db.get(OtaDeviceTask, ota_device_task_id)
    if not device_task or device_task.status != "upgrading":
        logger.warning(f"[{worker_name}] device_task {ota_device_task_id} not in 'upgrading' state, skipping")
        mark_processed(r, idempotency_key)
        return

    if random.random() < OTA_UPGRADE_SUCCESS_RATE:
        device_task.status = "success"
        device_task.completed_at = datetime.utcnow()
        device = db.execute(
            select(Device).where(Device.device_id == device_task.device_id)
        ).scalar_one_or_none()
        if device:
            device.kernel_version = device_task.target_version
        logger.info(f"[{worker_name}] SUCCESS device_task {ota_device_task_id}")
    else:
        device_task.status = "failed"
        device_task.error_message = random.choice(OTA_FAILURE_MESSAGES)
        device_task.completed_at = datetime.utcnow()
        logger.info(f"[{worker_name}] FAILED device_task {ota_device_task_id}: {device_task.error_message}")

    db.commit()
    mark_processed(r, idempotency_key)
