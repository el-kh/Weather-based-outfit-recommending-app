from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from .models import User
from fastapi import Response
from datetime import datetime, timedelta
from jose import jwt
from sqlalchemy import select
from .models import User

# Secret and algorithm (reuse same as your login logic)
SECRET_KEY = "your-secret-key"          # TODO: use env var
ALGORITHM = "HS256"

# Token lifetimes (same as in your login system)
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
RESET_TOKEN_EXPIRE_HOURS = 1
ACCESS_TTL_MIN = ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TTL_DAYS = REFRESH_TOKEN_EXPIRE_DAYS
ACTIVATE_TTL_HOURS = 24


# --------------------------------------------------------
# 🔐 JWT verification and creation helpers
# --------------------------------------------------------
def verify_token(token: str, expected_type: str):
    """
    Decode and validate a JWT token. 
    Ensures it matches the expected token type ('access', 'refresh', or 'reset').
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type:
            raise HTTPException(401, f"Invalid token type: expected {expected_type}")
        if payload.get("exp") and datetime.utcfromtimestamp(payload["exp"]) < datetime.utcnow():
            raise HTTPException(401, "Token expired")
        return payload
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")
    
    
def create_reset_token(user_id: int):
    from datetime import timedelta
    return make_token(str(user_id), timedelta(hours=1), "reset")



def make_token(user_id: int, expires_delta: timedelta, token_type: str):
    expire = datetime.utcnow() + expires_delta
    jti = f"{datetime.utcnow().timestamp()}-{user_id}"

    if token_type not in {"access", "refresh", "activate", "reset"}:
        raise ValueError("Invalid token type")

    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": jti,
        "iat": datetime.utcnow(),
        "exp": expire,
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, jti, expire

def cookie_tokens(response: Response, access_token: str, refresh_token: str):
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=False,  # True only in production (HTTPS)
        path="/",      
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        samesite="lax",
        secure=False,
        path="/",       
    )
    return response



# --------------------------------------------------------
# 👤 DB helpers
# --------------------------------------------------------


async def get_user_by_id(user_id: int, db: AsyncSession):
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

async def get_user_by_email(email: str, db: AsyncSession):
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

# --------------------------------------------------------
# 👥 Dependency: current user (based on middleware)
# --------------------------------------------------------
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Extract user info from request.state.user_id (set by AuthMiddleware)
    and fetch full user record.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Not authenticated")

    user = await get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(404, "User not found")
    return user
