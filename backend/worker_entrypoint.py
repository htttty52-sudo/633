import signal
import sys
import uuid
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("worker")

from app.redis_client import get_redis
from app.redis_streams import ensure_consumer_group, consume_tasks, acknowledge_message, claim_stale_messages
from app.worker import process_message
from app.worker_health import register_heartbeat
from app.database import SessionLocal
from app.config import WORKER_HEARTBEAT_INTERVAL

CONSUMER_NAME = f"worker-{uuid.uuid4().hex[:8]}"


def main():
    logger.info(f"Worker {CONSUMER_NAME} starting...")
    r = get_redis()
    ensure_consumer_group(r)

    running = True

    def shutdown(sig, frame):
        nonlocal running
        logger.info(f"Worker {CONSUMER_NAME} received shutdown signal")
        running = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    last_heartbeat = 0
    last_claim_check = 0

    logger.info(f"Worker {CONSUMER_NAME} ready, consuming from stream...")

    while running:
        now = time.time()

        if now - last_heartbeat > WORKER_HEARTBEAT_INTERVAL:
            register_heartbeat(r, CONSUMER_NAME)
            last_heartbeat = now

        # Periodically try to claim stale messages from crashed workers
        if now - last_claim_check > 60:
            claimed = claim_stale_messages(r, CONSUMER_NAME, min_idle_ms=120000, count=5)
            if claimed and len(claimed) > 1 and claimed[1]:
                logger.info(f"Worker {CONSUMER_NAME} claimed {len(claimed[1])} stale messages")
                for msg_id, fields in claimed[1]:
                    db = SessionLocal()
                    try:
                        process_message(db, r, fields, CONSUMER_NAME)
                        acknowledge_message(r, msg_id)
                    except Exception as e:
                        logger.error(f"Worker {CONSUMER_NAME} error processing claimed {msg_id}: {e}")
                    finally:
                        db.close()
            last_claim_check = now

        messages = consume_tasks(r, CONSUMER_NAME, batch_size=5, block_ms=2000)
        if not messages:
            continue

        for stream, entries in messages:
            for msg_id, fields in entries:
                db = SessionLocal()
                try:
                    process_message(db, r, fields, CONSUMER_NAME)
                    acknowledge_message(r, msg_id)
                except Exception as e:
                    logger.error(f"Worker {CONSUMER_NAME} error on {msg_id}: {e}")
                finally:
                    db.close()

    logger.info(f"Worker {CONSUMER_NAME} shutdown complete")


if __name__ == "__main__":
    main()
