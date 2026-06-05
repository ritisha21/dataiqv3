from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as aioredis
from app.core.config import settings
import time

RATE_LIMIT_RULES = {
    "/api/v1/query": (30, 60),       # 30 requests per 60 seconds
    "/api/v1/chat": (20, 60),
    "/api/v1/models/train": (5, 300),  # 5 per 5 minutes
    "/api/v1/connections/connect-db": (10, 60),
    "default": (100, 60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_url: str = None):
        super().__init__(app)
        self.redis_url = redis_url or settings.REDIS_URL

    async def dispatch(self, request: Request, call_next):
        # Extract tenant_id from JWT if available (best-effort)
        tenant_id = "anonymous"
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                from app.core.security import decode_token
                payload = decode_token(auth[7:])
                tenant_id = payload.get("tenant_id", "anonymous")
            except Exception:
                pass

        path = request.url.path
        limit, window = RATE_LIMIT_RULES.get(path, RATE_LIMIT_RULES["default"])

        key = f"rate:{tenant_id}:{path}"

        try:
            redis = aioredis.from_url(self.redis_url, decode_responses=True)
            pipe = redis.pipeline()
            now = int(time.time())
            window_start = now - window

            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, window)
            results = await pipe.execute()

            current_count = results[1]
            await redis.aclose()

            if current_count >= limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Max {limit} requests per {window}s.",
                    headers={"Retry-After": str(window)},
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Don't block requests if Redis is down

        response = await call_next(request)
        return response
