from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError
from app.core.security import decode_token
from app.db.database import get_db
from app.domain.models.models import User, Tenant, UserRole
import structlog

logger = structlog.get_logger()
security = HTTPBearer(auto_error=False)

# ── DEV BYPASS ────────────────────────────────────────────────────────────────
# Set to True to skip all auth checks in development.
# NEVER set this to True in production.
DEV_BYPASS_AUTH = True

DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEV_USER_ID   = "00000000-0000-0000-0000-000000000002"
DEV_ROLE      = UserRole.admin
# ─────────────────────────────────────────────────────────────────────────────


class TenantContext:
    def __init__(self, tenant_id: str, user_id: str, role: UserRole):
        self.tenant_id = tenant_id
        self.user_id   = user_id
        self.role      = role


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if DEV_BYPASS_AUTH:
        # Return a mock user object — no DB hit needed
        mock = User()
        mock.id        = DEV_USER_ID
        mock.tenant_id = DEV_TENANT_ID
        mock.role      = DEV_ROLE
        mock.is_active = True
        return mock

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise credentials_exception
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_tenant_context(
    current_user: User = Depends(get_current_user),
) -> TenantContext:
    return TenantContext(
        tenant_id = str(current_user.tenant_id),
        user_id   = str(current_user.id),
        role      = current_user.role,
    )


def require_role(*roles: UserRole):
    async def role_checker(
        ctx: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        if DEV_BYPASS_AUTH:
            return ctx
        if ctx.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {ctx.role} is not permitted",
            )
        return ctx
    return role_checker


require_admin             = require_role(UserRole.admin)
require_analyst_or_admin  = require_role(UserRole.admin, UserRole.analyst)
