import logging

import redis as redis_lib

logger = logging.getLogger(__name__)


def acquire_processing_lock(r: redis_lib.Redis, key: str, ttl: int = 120) -> bool:
    lock_key = f"idem:lock:{key}"
    acquired = r.set(lock_key, "1", nx=True, ex=ttl)
    if acquired:
        logger.debug(f"Lock acquired: {key}")
    else:
        logger.debug(f"Lock already held: {key}")
    return acquired is not None


def release_processing_lock(r: redis_lib.Redis, key: str):
    lock_key = f"idem:lock:{key}"
    r.delete(lock_key)


def mark_processed(r: redis_lib.Redis, key: str):
    processed_key = f"idem:done:{key}"
    r.setex(processed_key, 86400, "1")
    release_processing_lock(r, key)
    logger.debug(f"Marked processed: {key}")


def is_already_processed(r: redis_lib.Redis, key: str) -> bool:
    return r.exists(f"idem:done:{key}") == 1


def generate_idempotency_key(device_task_id: int, attempt_count: int) -> str:
    return f"ota_dt:{device_task_id}:attempt:{attempt_count}"
