import os
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

# Store refresh token jti -> user_id (with TTL), and a denylist for access jti at logout
async def store_refresh(jti: str, user_id: int, seconds: int):
    await r.setex(f"rt:{jti}", seconds, str(user_id))

async def take_refresh(jti: str):
    key = f"rt:{jti}"
    # emulate GETDEL for Redis < 6.2
    async with r.pipeline(transaction=True) as pipe:
        pipe.get(key)
        pipe.delete(key)
        result, _ = await pipe.execute()
        return result

async def deny_access(jti: str, seconds: int):
    await r.setex(f"blk:{jti}", seconds, "1")

async def is_denied(jti: str) -> bool:
    return bool(await r.exists(f"blk:{jti}"))
