import os
import bcrypt
import jwt
from fastapi import HTTPException, Request, Response
from datetime import datetime, timezone, timedelta
from database import db

# Fail-fast on missing/weak JWT secret. A 64-char hex is our default seed
# length; accept anything >= 32 chars to also allow sufficiently long random
# strings. This runs at import-time so a missing secret trips the container
# before any request is served.
JWT_SECRET = os.environ.get("JWT_SECRET") or ""
if len(JWT_SECRET) < 32:
    raise RuntimeError(
        "JWT_SECRET is missing or too short (>= 32 chars required). "
        "Set the JWT_SECRET environment variable to a strong random value."
    )
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def create_access_token(user_id: str, email: str, token_version: int = 0) -> str:
    return jwt.encode({
        "user_id": user_id, "email": email,
        "tv": int(token_version or 0),
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str, token_version: int = 0) -> str:
    return jwt.encode({
        "user_id": user_id,
        "tv": int(token_version or 0),
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
        "type": "refresh",
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)

def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie("access_token", access_token, httponly=True, samesite="none", secure=True, max_age=86400)
    response.set_cookie("refresh_token", refresh_token, httponly=True, samesite="none", secure=True, max_age=2592000)

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # iter 202 — short-lived per-request user cache (5s TTL) to avoid
        # hammering MongoDB on bursty traffic. Hot-path optimization for
        # /user/permissions, /tasks/pending-count etc.
        from services import user_cache
        user = await user_cache.get(payload["user_id"])
        if user is None:
            user = await db.users.find_one({"user_id": payload["user_id"]}, {"_id": 0, "password_hash": 0})
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            await user_cache.set(payload["user_id"], user)
        # Session invalidation: if an admin bumped `token_version`, tokens
        # issued before the bump (lower `tv`) are rejected.
        token_tv = int(payload.get("tv", 0) or 0)
        user_tv = int(user.get("token_version", 0) or 0)
        if token_tv < user_tv:
            raise HTTPException(status_code=401, detail="Session invalidated")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def user_response(user: dict) -> dict:
    # Iter 188 — also strip TOTP secrets and recovery hashes so they NEVER
    # leak via /auth/me, /auth/login, /auth/2fa/verify-login responses.
    HIDDEN = {
        "password_hash", "_id",
        "totp_secret", "totp_pending_secret",
        "totp_recovery_hashes", "totp_pending_recovery_hashes",
    }
    return {k: v for k, v in user.items() if k not in HIDDEN}
