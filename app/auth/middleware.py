from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from .deps import verify_token
from .redis_store import is_denied

SKIP_PREFIXES = ("/auth/", "/docs", "/redoc", "/openapi.json", "/healthz")

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return await call_next(request)

        tok = request.cookies.get("access_token")
        if not tok:
            raise HTTPException(401, "Missing token")

        p = verify_token(tok, "access")
        if await is_denied(p["jti"]):
            raise HTTPException(401, "Revoked")

        request.state.user_id = int(p["sub"])
        return await call_next(request)
