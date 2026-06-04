import random
import logging
import threading
from datetime import datetime

import redis as redis_lib
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device
from app.ota_models import OtaDeviceTask
from app.config import OTA_UPGRADE_SUCCESS_RATE

logger = logging.getLogger(__name__)

PROCESSED_SET_KEY = "ota:processed_task_ids"
TASK_LOCK_PREFIX = "ota:lock:task:"
LOCK_INITIAL_TTL = 15
LOCK_RENEW_INTERVAL = 5

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


class LockRenewer:
    """Renews a Redis key's TTL every interval until stopped."""

    def __init__(self, r: redis_lib.Redis, lock_key: str, interval: int = LOCK_RENEW_INTERVAL):
        self._r = r
        self._lock_key = lock_key
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._thread.join(timeout=2)

    def _run(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._interval)
            if self._stop_event.is_set():
                break
            self._r.expire(self._lock_key, LOCK_INITIAL_TTL)


def process_message(db: Session, r: redis_lib.Redis, fields: dict, worker_name: str):
    ota_device_task_id = int(fields["ota_device_task_id"])
    task_id_str = str(ota_device_task_id)

    # Step 1: Already processed? Skip.
    if r.sismember(PROCESSED_SET_KEY, task_id_str):
        logger.info(f"[{worker_name}] SKIP already processed task_id={ota_device_task_id}")
        return

    # Step 2: Acquire lock (SET NX with initial TTL, renewed by background thread)
    lock_key = f"{TASK_LOCK_PREFIX}{ota_device_task_id}"
    acquired = r.set(lock_key, worker_name, nx=True, ex=LOCK_INITIAL_TTL)
    if not acquired:
        logger.info(f"[{worker_name}] SKIP locked by another worker task_id={ota_device_task_id}")
        return

    # Start lock renewal thread
    renewer = LockRenewer(r, lock_key)
    renewer.start()

    logger.info(f"[{worker_name}] Processing task_id={ota_device_task_id}")

    try:
        device_task = db.get(OtaDeviceTask, ota_device_task_id)
        if not device_task or device_task.status != "upgrading":
            logger.warning(f"[{worker_name}] task_id={ota_device_task_id} not in 'upgrading' state, marking done")
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

        # Mark as processed
        r.sadd(PROCESSED_SET_KEY, task_id_str)
        logger.info(f"[{worker_name}] DONE task_id={ota_device_task_id}")

    except Exception as e:
        db.rollback()
        raise
    finally:
        # Stop renewal and release lock
        renewer.stop()
        r.delete(lock_key)
