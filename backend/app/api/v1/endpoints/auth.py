from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import hashlib
import uuid

from app.db.database import get_db
from app.domain.models.models import User, Tenant, RefreshToken, UserRole
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token
)
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    tenant_name: str
    tenant_slug: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    tenant_id: str
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check tenant slug uniqueness
    existing_tenant = await db.execute(select(Tenant).where(Tenant.slug == req.tenant_slug))
    if existing_tenant.scalar_one_or_none():
        raise HTTPException(400, "Tenant slug already taken")

    tenant = Tenant(name=req.tenant_name, slug=req.tenant_slug)
    db.add(tenant)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=req.email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        role=UserRole.admin,
    )
    db.add(user)
    await db.flush()

    tokens = _issue_tokens(user, tenant)
    await _store_refresh_token(db, user.id, tokens["refresh_token"])
    await db.commit()
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    tenant_result = await db.execute(select(Tenant).where(Tenant.slug == req.tenant_slug))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(401, "Invalid credentials")

    user_result = await db.execute(
        select(User).where(User.email == req.email, User.tenant_id == tenant.id, User.is_active == True)
    )
    user = user_result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")

    user.last_login = datetime.utcnow()
    tokens = _issue_tokens(user, tenant)
    await _store_refresh_token(db, user.id, tokens["refresh_token"])
    await db.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(401, "Invalid token type")
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(401, "Invalid refresh token")

    token_hash = hashlib.sha256(req.refresh_token.encode()).hexdigest()
    rt_result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False,
        )
    )
    rt = rt_result.scalar_one_or_none()
    if not rt or rt.expires_at < datetime.utcnow():
        raise HTTPException(401, "Refresh token expired or revoked")

    rt.revoked = True

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = tenant_result.scalar_one()

    tokens = _issue_tokens(user, tenant)
    await _store_refresh_token(db, user.id, tokens["refresh_token"])
    await db.commit()
    return tokens


def _issue_tokens(user: User, tenant: Tenant) -> dict:
    payload = {"sub": str(user.id), "tenant_id": str(tenant.id), "role": user.role.value}
    return {
        "access_token": create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
        "token_type": "bearer",
        "user_id": str(user.id),
        "tenant_id": str(tenant.id),
        "role": user.role.value,
    }


async def _store_refresh_token(db: AsyncSession, user_id, token: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    rt = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(rt)
