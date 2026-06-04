import random
import logging
from datetime import datetime

import redis as redis_lib
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device
from app.ota_models import OtaDeviceTask
from app.config import OTA_UPGRADE_SUCCESS_RATE

logger = logging.getLogger(__name__)

# Redis key for the SET of all processed task IDs
PROCESSED_SET_KEY = "ota:processed_task_ids"
# Redis key prefix for per-task processing lock
TASK_LOCK_PREFIX = "ota:lock:task:"

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
    ota_device_task_id = int(fields["ota_device_task_id"])
    task_id_str = str(ota_device_task_id)

    # Step 1: Check if this task ID was already processed (Redis SET lookup)
    if r.sismember(PROCESSED_SET_KEY, task_id_str):
        logger.info(f"[{worker_name}] SKIP already processed task_id={ota_device_task_id}")
        return

    # Step 2: Acquire per-task lock (SET NX with TTL) to prevent concurrent processing
    lock_key = f"{TASK_LOCK_PREFIX}{ota_device_task_id}"
    acquired = r.set(lock_key, worker_name, nx=True, ex=120)
    if not acquired:
        logger.info(f"[{worker_name}] SKIP locked by another worker task_id={ota_device_task_id}")
        return

    logger.info(f"[{worker_name}] Processing task_id={ota_device_task_id}")

    try:
        device_task = db.get(OtaDeviceTask, ota_device_task_id)
        if not device_task or device_task.status != "upgrading":
            logger.warning(f"[{worker_name}] task_id={ota_device_task_id} not in 'upgrading' state, marking done")
            # Still mark as processed so we don't retry
            r.sadd(PROCESSED_SET_KEY, task_id_str)
            return

        if random.random() < OTA_UPGRADE_SUCCESS_RATE:
            device_task.status = "success"
            device_task.completed_at = datetime.utcnow()
            device = db.execute(
                select(Device).where(Device.device_id == device_task.device_id)
            ).scalar_one_or_none()
            if device:
                device.kernel_version = device_task.target_version
            logger.info(f"[{worker_name}] SUCCESS task_id={ota_device_task_id}")
        else:
            device_task.status = "failed"
            device_task.error_message = random.choice(OTA_FAILURE_MESSAGES)
            device_task.completed_at = datetime.utcnow()
            logger.info(f"[{worker_name}] FAILED task_id={ota_device_task_id}: {device_task.error_message}")

        db.commit()

        # Step 3: After successful DB commit, record this task as processed
        r.sadd(PROCESSED_SET_KEY, task_id_str)
        logger.info(f"[{worker_name}] DONE task_id={ota_device_task_id} recorded in processed set")

    except Exception as e:
        db.rollback()
        # Release lock on error so another worker can retry
        r.delete(lock_key)
        raise
