from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, EmailStr, constr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from .models import User
from .hash import hash_pw, verify_pw
from .deps import (
    make_token, verify_token, cookie_tokens,
    ACCESS_TTL_MIN, REFRESH_TTL_DAYS, ACTIVATE_TTL_HOURS
)
from .redis_store import store_refresh, take_refresh, deny_access

router = APIRouter(prefix="/auth", tags=["auth"])

# For local dev over http you usually want secure=False; in prod set True.
COOKIE_OPTS = {"httponly": True, "secure": False, "samesite": "lax", "path": "/"}

class RegisterIn(BaseModel):
    email: EmailStr
    password: constr(min_length=8)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

@router.post("/register")
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    exists = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if exists:
        raise HTTPException(400, "Email already registered")
    user = User(email=body.email, password_hash=hash_pw(body.password), is_active=False)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # For HW/demo: return activation token so you can test activation without email
    activate_token, _ = make_token(str(user.id), timedelta(hours=ACTIVATE_TTL_HOURS), "activate")
    return {
        "message": "Account created. Use /auth/activate?token=... to activate.",
        "activate_token": activate_token
    }

@router.get("/activate")
async def activate(token: str, db: AsyncSession = Depends(get_db)):
    payload = verify_token(token, "activate")
    user = await db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(400, "User not found")
    user.is_active = True
    await db.commit()
    return {"message": "Account activated"}

@router.post("/login")
async def login(body: LoginIn, response: Response, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if not user or not verify_pw(user.password_hash, body.password) or not user.is_active:
        raise HTTPException(401, "Invalid credentials or inactive account")

    access, access_jti = make_token(str(user.id), timedelta(minutes=ACCESS_TTL_MIN), "access")
    refresh, refresh_jti = make_token(str(user.id), timedelta(days=REFRESH_TTL_DAYS), "refresh")
    await store_refresh(refresh_jti, user.id, REFRESH_TTL_DAYS * 24 * 3600)

    response.set_cookie("access_token", access, **COOKIE_OPTS, max_age=ACCESS_TTL_MIN * 60)
    response.set_cookie("refresh_token", refresh, **COOKIE_OPTS, max_age=REFRESH_TTL_DAYS * 24 * 3600)
    return {"message": "Logged in"}

@router.post("/refresh")
async def refresh(request: Request, response: Response):
    _, rtk = cookie_tokens(request)
    if not rtk:
        raise HTTPException(401, "Missing refresh")

    payload = verify_token(rtk, "refresh")
    user_id = await take_refresh(payload["jti"])  # must exist (rotation)
    if not user_id:
        raise HTTPException(401, "Stale refresh")

    access, _ = make_token(str(user_id), timedelta(minutes=ACCESS_TTL_MIN), "access")
    refresh, refresh_jti = make_token(str(user_id), timedelta(days=REFRESH_TTL_DAYS), "refresh")
    await store_refresh(refresh_jti, int(user_id), REFRESH_TTL_DAYS * 24 * 3600)

    response.set_cookie("access_token", access, **COOKIE_OPTS, max_age=ACCESS_TTL_MIN * 60)
    response.set_cookie("refresh_token", refresh, **COOKIE_OPTS, max_age=REFRESH_TTL_DAYS * 24 * 3600)
    return {"message": "Refreshed"}

@router.post("/logout")
async def logout(request: Request, response: Response):
    atk, rtk = cookie_tokens(request)
    if atk:
        p = verify_token(atk, "access")
        ttl = p["exp"] - p["iat"]
        await deny_access(p["jti"], ttl)
    if rtk:
        p = verify_token(rtk, "refresh")
        await take_refresh(p["jti"])

    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}
