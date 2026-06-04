import logging
from datetime import datetime

import redis as redis_lib

from app.config import WORKER_HEARTBEAT_INTERVAL

logger = logging.getLogger(__name__)

WORKER_KEY_PREFIX = "worker:heartbeat:"
WORKER_TTL = WORKER_HEARTBEAT_INTERVAL * 3


def register_heartbeat(r: redis_lib.Redis, worker_name: str):
    key = f"{WORKER_KEY_PREFIX}{worker_name}"
    r.setex(key, WORKER_TTL, datetime.utcnow().isoformat())


def get_active_workers(r: redis_lib.Redis) -> list[dict]:
    workers = []
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match=f"{WORKER_KEY_PREFIX}*", count=100)
        for key in keys:
            name = key.replace(WORKER_KEY_PREFIX, "")
            last_seen = r.get(key)
            ttl = r.ttl(key)
            workers.append({
                "name": name,
                "last_heartbeat": last_seen,
                "is_alive": ttl > 0,
            })
        if cursor == 0:
            break
    return workers
