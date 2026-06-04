import logging
from datetime import datetime

import redis as redis_lib

from app.config import WORKER_GROUP_NAME

logger = logging.getLogger(__name__)

STREAM_NAME = "ota:device_tasks"


def ensure_consumer_group(r: redis_lib.Redis):
    try:
        r.xgroup_create(STREAM_NAME, WORKER_GROUP_NAME, id="0", mkstream=True)
        logger.info(f"Created consumer group '{WORKER_GROUP_NAME}' on stream '{STREAM_NAME}'")
    except redis_lib.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
        logger.info(f"Consumer group '{WORKER_GROUP_NAME}' already exists")


def publish_device_task(r: redis_lib.Redis, ota_device_task_id: int, idempotency_key: str):
    msg_id = r.xadd(STREAM_NAME, {
        "ota_device_task_id": str(ota_device_task_id),
        "idempotency_key": idempotency_key,
        "published_at": datetime.utcnow().isoformat(),
    })
    logger.info(f"Published device_task {ota_device_task_id} to stream, msg_id={msg_id}")
    return msg_id


def consume_tasks(r: redis_lib.Redis, consumer_name: str, batch_size: int = 5, block_ms: int = 2000):
    messages = r.xreadgroup(
        groupname=WORKER_GROUP_NAME,
        consumername=consumer_name,
        streams={STREAM_NAME: ">"},
        count=batch_size,
        block=block_ms,
    )
    return messages


def acknowledge_message(r: redis_lib.Redis, msg_id: str):
    r.xack(STREAM_NAME, WORKER_GROUP_NAME, msg_id)


def get_stream_info(r: redis_lib.Redis) -> dict:
    try:
        stream_info = r.xinfo_stream(STREAM_NAME)
        groups_info = r.xinfo_groups(STREAM_NAME)
    except redis_lib.exceptions.ResponseError:
        return {"stream_length": 0, "groups": []}

    groups = []
    for g in groups_info:
        groups.append({
            "name": g.get("name", ""),
            "consumers": g.get("consumers", 0),
            "pending": g.get("pending", 0),
            "last_delivered_id": g.get("last-delivered-id", ""),
        })

    return {
        "stream_length": stream_info.get("length", 0),
        "first_entry": stream_info.get("first-entry"),
        "last_entry": stream_info.get("last-entry"),
        "groups": groups,
    }


def claim_stale_messages(r: redis_lib.Redis, consumer_name: str, min_idle_ms: int = 120000, count: int = 10):
    try:
        result = r.xautoclaim(STREAM_NAME, WORKER_GROUP_NAME, consumer_name, min_idle_time=min_idle_ms, count=count)
        return result
    except Exception:
        return None
