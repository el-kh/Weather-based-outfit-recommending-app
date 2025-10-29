from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request
import jwt, uuid, os

ALGO = "HS256"
ACCESS_TTL_MIN = 15
REFRESH_TTL_DAYS = 7
ACTIVATE_TTL_HOURS = 24

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")

def _now() -> datetime:
    return datetime.now(timezone.utc)

def make_token(sub: str, ttl: timedelta, typ: str, extra: dict | None = None):
    jti = str(uuid.uuid4())
    payload = {
        "sub": sub,
        "jti": jti,
        "type": typ,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + ttl).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGO), jti

def verify_token(token: str, typ: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGO])
        if payload.get("type") != typ:
            raise jwt.InvalidTokenError("Wrong type")
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def cookie_tokens(request: Request):
    return (request.cookies.get("access_token"), request.cookies.get("refresh_token"))
