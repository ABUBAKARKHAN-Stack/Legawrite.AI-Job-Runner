import redis.asyncio as redis
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Singleton client — one connection pool shared across the entire process.
# Creating a new client on every request leaks connections and defeats pooling.
_redis_client: redis.Redis | None = None

async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client
