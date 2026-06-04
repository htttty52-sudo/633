import random
import logging
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Device
from app.config import HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(
    executors={
        "heartbeat": ThreadPoolExecutor(max_workers=2),
        "default": ThreadPoolExecutor(max_workers=2),
    }
)

_heartbeat_lock = threading.Lock()


def simulate_heartbeat():
    """Independently manages device heartbeat. Runs in its own thread pool executor,
    completely decoupled from OTA upgrade operations.
    Devices in 'upgrading' state always get heartbeat updated (100% probability)."""
    if not _heartbeat_lock.acquire(blocking=False):
        return
    try:
        db = SessionLocal()
        try:
            from app.ota_crud import get_upgrading_device_ids_cached
            upgrading_ids = get_upgrading_device_ids_cached()

            devices = db.execute(select(Device)).scalars().all()
            if not devices:
                return

            now = datetime.utcnow()
            for device in devices:
                if device.device_id in upgrading_ids:
                    device.last_heartbeat = now
                    continue

                elapsed = (now - device.last_heartbeat).total_seconds()
                if elapsed < HEARTBEAT_TIMEOUT:
                    if random.random() < 0.7:
                        device.last_heartbeat = now

            db.commit()
            logger.info(f"Heartbeat simulation completed for {len(devices)} devices")
        except Exception as e:
            db.rollback()
            logger.error(f"Heartbeat simulation error: {e}")
        finally:
            db.close()
    finally:
        _heartbeat_lock.release()


def check_offline_devices():
    """Compare current time with each device's last_heartbeat.
    If the difference exceeds HEARTBEAT_TIMEOUT, mark as offline; otherwise mark as online.
    Runs independently in default thread pool."""
    db = SessionLocal()
    try:
        devices = db.execute(select(Device)).scalars().all()
        if not devices:
            return

        now = datetime.utcnow()
        changed = 0
        for device in devices:
            elapsed = (now - device.last_heartbeat).total_seconds()
            new_status = elapsed <= HEARTBEAT_TIMEOUT
            if device.is_online != new_status:
                device.is_online = new_status
                changed += 1

        if changed > 0:
            db.commit()
            logger.info(f"Status updated: {changed} devices changed (timeout={HEARTBEAT_TIMEOUT}s)")
        else:
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Offline check error: {e}")
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        simulate_heartbeat, "interval",
        seconds=HEARTBEAT_INTERVAL,
        id="heartbeat_simulation",
        executor="heartbeat",
    )
    scheduler.add_job(
        check_offline_devices, "interval",
        seconds=HEARTBEAT_INTERVAL,
        id="offline_check",
        executor="default",
    )
    scheduler.start()
    logger.info(f"Scheduler started: heartbeat every {HEARTBEAT_INTERVAL}s, timeout {HEARTBEAT_TIMEOUT}s")


def stop_scheduler():
    scheduler.shutdown(wait=False)
