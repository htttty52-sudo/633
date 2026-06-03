import random
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Device
from app.config import HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT
from app.crud import check_heartbeat_timeout

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def simulate_heartbeat():
    """Every HEARTBEAT_INTERVAL seconds, randomly update device heartbeats to simulate real devices."""
    db = SessionLocal()
    try:
        devices = db.execute(select(Device)).scalars().all()
        if not devices:
            return

        for device in devices:
            # 70% chance the device sends a heartbeat (stays online)
            if random.random() < 0.7:
                device.last_heartbeat = datetime.utcnow()
                device.is_online = True
            # 30% chance no heartbeat - will eventually time out

        db.commit()
        logger.info(f"Heartbeat simulation completed for {len(devices)} devices")
    except Exception as e:
        db.rollback()
        logger.error(f"Heartbeat simulation error: {e}")
    finally:
        db.close()


def check_offline_devices():
    """Check for devices that have timed out and mark them offline."""
    db = SessionLocal()
    try:
        count = check_heartbeat_timeout(db, HEARTBEAT_TIMEOUT)
        if count > 0:
            logger.info(f"Marked {count} devices as offline due to heartbeat timeout")
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
