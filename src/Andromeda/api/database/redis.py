import redis.asyncio as redis
from Andromeda.config import settings

pool = redis.ConnectionPool.from_url(
    settings.redis_url,
    decode_responses=True
)

redis_client = redis.Redis(connection_pool=pool)
