import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, hash_token, decode_access_token
from app.core.config import get_settings
from app.models.user import User, RefreshToken

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
security = HTTPBearer()
settings = get_settings()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    user_id: str
    email: str
    name: str
    tier: str
    access_token: str
    refresh_token: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == uuid.UUID(payload["sub"]), User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _auth_response(user: User, access_token: str, refresh_token: str) -> AuthResponse:
    return AuthResponse(user_id=str(user.id), email=user.email, name=user.name, tier=user.tier,
                        access_token=access_token, refresh_token=refresh_token)


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email, hashed_password=hash_password(body.password), name=body.name)
    db.add(user)
    await db.flush()
    access = create_access_token({"sub": str(user.id), "email": user.email, "tier": user.tier})
    raw_rt, hashed_rt = create_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hashed_rt,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=30)))
    await db.commit()
    return _auth_response(user, access, raw_rt)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access = create_access_token({"sub": str(user.id), "email": user.email, "tier": user.tier})
    raw_rt, hashed_rt = create_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hashed_rt,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=30)))
    await db.commit()
    return _auth_response(user, access, raw_rt)


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"user_id": str(user.id), "email": user.email, "name": user.name, "tier": user.tier}
