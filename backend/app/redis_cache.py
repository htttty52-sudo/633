import json
from typing import Any, Optional

from app.redis_client import get_redis
from app.config import REDIS_CACHE_TTL


def cache_get(key: str) -> Optional[Any]:
    r = get_redis()
    data = r.get(f"cache:{key}")
    if data is None:
        return None
    return json.loads(data)


def cache_set(key: str, value: Any, ttl: int = REDIS_CACHE_TTL):
    r = get_redis()
    r.setex(f"cache:{key}", ttl, json.dumps(value, default=str))


def cache_invalidate(pattern: str):
    r = get_redis()
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match=f"cache:{pattern}*", count=100)
        if keys:
            r.delete(*keys)
        if cursor == 0:
            break
