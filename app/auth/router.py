from datetime import timedelta, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from .models import User
from .deps import (
    make_token, verify_token, cookie_tokens,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, ACTIVATE_TTL_HOURS,
    create_reset_token, get_current_user
)
from .redis_store import store_refresh, take_refresh, deny_access, r
from .hash import verify_password, hash_password


router = APIRouter(prefix="/auth", tags=["auth"])

# Local dev = secure=False; in production set True
COOKIE_OPTS = {"httponly": True, "secure": False, "samesite": "lax", "path": "/"}


# -------------------------------------------------------------------
# 📩 Register & Activate
# -------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/register")
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    exists = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if exists:
        raise HTTPException(400, "Email already registered")

    user = User(email=body.email, password_hash=hash_password(body.password), is_active=False)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Create activation token
    activate_token, _, _ = make_token(str(user.id), timedelta(hours=ACTIVATE_TTL_HOURS), "activate")

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
    return {"message": "Account activated successfully"}


# -------------------------------------------------------------------
# 🔐 Login / Refresh / Logout
# -------------------------------------------------------------------
class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
async def login(body: LoginIn, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "Invalid email or password")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

    if not user.is_active:
        raise HTTPException(403, "Account not activated")

    # Generate tokens
    access_token, access_jti, _ = make_token(
        str(user.id), timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES), "access"
    )
    refresh_token, refresh_jti, _ = make_token(
        str(user.id), timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), "refresh"
    )

    # Store refresh token in Redis
    await store_refresh(refresh_jti, user.id, REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)

    # Set cookies for browsers
    cookie_tokens(response, access_token, refresh_token)

    return {
        "message": "Logged in successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    # Try cookie first
    refresh_token = request.cookies.get("refresh_token")

    # Try Authorization header fallback
    if not refresh_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            refresh_token = auth_header.split(" ")[1]

    if not refresh_token:
        raise HTTPException(401, "Missing refresh token")

    # Verify and rotate
    payload = verify_token(refresh_token, "refresh")
    user_id = await take_refresh(payload["jti"])
    if not user_id:
        raise HTTPException(401, "Stale or invalid refresh")

    new_access, new_access_jti, _ = make_token(
        str(user_id), timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES), "access"
    )
    new_refresh, new_refresh_jti, _ = make_token(
        str(user_id), timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), "refresh"
    )

    await store_refresh(new_refresh_jti, int(user_id), REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)

    # Set new cookies
    cookie_tokens(response, new_access, new_refresh)
    return {"message": "Refreshed successfully"}


@router.post("/logout")
async def logout(request: Request, response: Response):
    atk = request.cookies.get("access_token")
    rtk = request.cookies.get("refresh_token")

    if atk:
        p = verify_token(atk, "access")
        ttl = int(p["exp"] - datetime.utcnow().timestamp())
        await deny_access(p["jti"], max(ttl, 0))

    if rtk:
        p = verify_token(rtk, "refresh")
        await take_refresh(p["jti"])

    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")

    return {"message": "Logged out successfully"}


# -------------------------------------------------------------------
# 💓 Health check
# -------------------------------------------------------------------
@router.get("/healthz")
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# -------------------------------------------------------------------
# 🔑 Change Password (requires login)
# -------------------------------------------------------------------
class PasswordChangeIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    payload: PasswordChangeIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(400, "Incorrect old password")

    user.password_hash = hash_password(payload.new_password)
    await db.commit()
    return {"detail": "Password changed successfully"}


# -------------------------------------------------------------------
# 🔁 Forgot / Reset Password
# -------------------------------------------------------------------
class ForgotPasswordIn(BaseModel):
    email: EmailStr

@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordIn, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    token = create_reset_token(user.id)
    reset_link = f"http://127.0.0.1:8000/auth/reset-password?token={token}"

    print(f"[DEBUG] Reset link: {reset_link}")

    # For now, return the link so frontend can use it
    return {
        "detail": "Password reset link generated",
        "reset_link": reset_link
    }



class ResetPasswordIn(BaseModel):
    token: Optional[str] = None
    new_password: Optional[str] = None


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordIn = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    # 1️⃣ Extract token (from JSON or query param)
    token = payload.token if payload and payload.token else request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Missing reset token")

    # 2️⃣ Verify token type = 'reset'
    try:
        payload_data = verify_token(token, "reset")
    except HTTPException as e:
        raise HTTPException(status_code=401, detail="Invalid or expired reset token")

    user_id = int(payload_data["sub"])
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 3️⃣ If no password provided (user just clicked the link)
    new_password = payload.new_password if payload else None
    if not new_password:
        return {
            "message": "Token verified. Please send POST with new_password to complete reset.",
            "user_id": user.id,
        }

    # 4️⃣ Hash and update password
    user.password_hash = hash_password(new_password)
    await db.commit()

    # 5️⃣ Optional — invalidate old tokens (logout everywhere)
    keys = await r.keys("rt:*")
    for k in keys:
        val = await r.get(k)
        if val == str(user.id):
            await r.delete(k)

    return {"detail": "Password reset successfully"}


@router.get("/reset-password")
async def verify_reset_token(token: str, db: AsyncSession = Depends(get_db)):
    try:
        payload = verify_token(token, "reset")
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid or expired reset token")

    user = await db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # You can later redirect this to your frontend (React, etc.)
    return {
        "message": "✅ Token valid. You can now submit your new password via POST /auth/reset-password",
        "user_email": user.email
    }


# -------------------------------------------------------------------
# 🚫 Revoke All Tokens
# -------------------------------------------------------------------
@router.post("/revoke-all")
async def revoke_all(user: User = Depends(get_current_user)):
    keys = await r.keys("rt:*")
    count = 0
    for k in keys:
        val = await r.get(k)
        if val == str(user.id):  # no .decode() needed (decode_responses=True)
            await r.delete(k)
            count += 1
    return {"detail": f"Revoked {count} refresh tokens"}


# -------------------------------------------------------------------
# 👤 Profile
# -------------------------------------------------------------------
class ProfileUpdateIn(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


@router.get("/profile")
async def get_profile(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "name": getattr(user, "name", None)}


@router.put("/profile")
async def update_profile(
    payload: ProfileUpdateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if payload.name:
        user.name = payload.name
    if payload.email:
        user.email = payload.email
    await db.commit()
    return {"detail": "Profile updated successfully"}


# -------------------------------------------------------------------
# 👤 /me (alias of /profile)
# -------------------------------------------------------------------
@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "name": getattr(user, "name", None)}
