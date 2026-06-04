import random
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Device
from app.config import HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def simulate_heartbeat():
    """Simulate device heartbeats: only update last_heartbeat for devices still within the timeout window.
    Devices that have already timed out won't randomly come back online.
    Devices currently being upgraded always get heartbeat updated."""
    db = SessionLocal()
    try:
        from app.ota_crud import get_upgrading_device_ids
        upgrading_ids = get_upgrading_device_ids(db)

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
                # Device is within the threshold - randomly decide if it sends a heartbeat
                if random.random() < 0.7:
                    device.last_heartbeat = now

        db.commit()
        logger.info(f"Heartbeat simulation completed for {len(devices)} devices")
    except Exception as e:
        db.rollback()
        logger.error(f"Heartbeat simulation error: {e}")
    finally:
        db.close()


def check_offline_devices():
    """Compare current time with each device's last_heartbeat.
    If the difference exceeds HEARTBEAT_TIMEOUT, mark as offline; otherwise mark as online."""
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
    scheduler.add_job(simulate_heartbeat, "interval", seconds=HEARTBEAT_INTERVAL, id="heartbeat_simulation")
    scheduler.add_job(check_offline_devices, "interval", seconds=HEARTBEAT_INTERVAL, id="offline_check")
    scheduler.start()
    logger.info(f"Scheduler started: heartbeat every {HEARTBEAT_INTERVAL}s, timeout {HEARTBEAT_TIMEOUT}s")


def stop_scheduler():
    scheduler.shutdown(wait=False)
