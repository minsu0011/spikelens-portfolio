import json
import logging

import redis

from app.core.config import get_settings

logger = logging.getLogger("spikelens")
redis_client = redis.Redis.from_url(
    get_settings().redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1
)


def get_public_summary():
    try:
        value = redis_client.get("spikelens:public:summary:v1")
        redis_client.incr(
            "spikelens:metrics:cache_hits" if value else "spikelens:metrics:cache_misses"
        )
        return json.loads(value) if value else None
    except (redis.RedisError, ValueError):
        return None


def set_public_summary(value):
    try:
        redis_client.setex(
            "spikelens:public:summary:v1",
            get_settings().summary_cache_ttl,
            json.dumps(value, default=str),
        )
    except redis.RedisError:
        logger.warning("public_cache_unavailable")


def invalidate_public_summary():
    try:
        redis_client.delete("spikelens:public:summary:v1")
    except redis.RedisError:
        pass
