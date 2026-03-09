import json
import redis.asyncio as aioredis
from app.config import settings

redis_client: aioredis.Redis = None


async def get_redis() -> aioredis.Redis:
    return redis_client

async def init_redis():
    global redis_client
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

async def close_redis():
    if redis_client:
        await redis_client.aclose()

async def cache_set(key: str, value: dict, ttl: int = 300):
    # сохраняем в кэш
    await redis_client.setex(key, ttl, json.dumps(value))

async def cache_get(key: str) -> dict | None:
    # берем из кэша, если нет - возвращает None
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return None

async def cache_delete(key: str):
    await redis_client.delete(key)
