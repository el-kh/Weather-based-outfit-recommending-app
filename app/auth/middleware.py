from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from app.auth.deps import verify_token

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = request.cookies.get("access_token")
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        print("[DEBUG] access_token:", token)  # 👈 add this

        request.state.user_id = None
        if token:
            try:
                payload = verify_token(token, "access")
                request.state.user_id = int(payload["sub"])
                print("[DEBUG] user_id from token:", request.state.user_id)
            except HTTPException as e:
                print("[DEBUG] Token verification failed:", e.detail)
                request.state.user_id = None

        response = await call_next(request)
        return response
