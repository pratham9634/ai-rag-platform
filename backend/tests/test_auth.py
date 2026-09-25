"""
Unit tests for Clerk JWT Multi-Tenant Authentication and RBAC.

Tests:
1. Fallback dev tenant resolution with and without X-Tenant-ID header.
2. Verified Clerk JWT decoding (sub, org_id -> tenant_id).
3. Expired token raises 401 Unauthorized.
4. RBAC role checking permits admin and rejects non-admin.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.security import (
    AuthenticatedUser,
    decode_clerk_jwt,
    get_current_tenant_id,
    get_current_user,
    require_role,
)


@pytest.mark.asyncio
async def test_auth_fallback_with_custom_tenant_header() -> None:
    """When no Bearer token is provided, should respect X-Tenant-ID header."""
    user = await get_current_user(credentials=None, x_tenant_id="tenant-beta")
    assert user.tenant_id == "tenant-beta"
    assert user.is_authenticated is False
    assert user.user_id == "dev-user"

    tenant_id = await get_current_tenant_id(user)
    assert tenant_id == "tenant-beta"


@pytest.mark.asyncio
async def test_auth_fallback_default_tenant() -> None:
    """When no credentials or header provided, defaults to 'default-tenant'."""
    user = await get_current_user(credentials=None, x_tenant_id=None)
    assert user.tenant_id == "default-tenant"


@pytest.mark.asyncio
async def test_bearer_token_org_tenant_resolution() -> None:
    """Valid JWT with org_id should derive tenant_id directly from org_id."""
    payload = {
        "sub": "user_2test123",
        "org_id": "org_enterprise_99",
        "org_role": "org:admin",
        "org_slug": "acme-corp",
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }
    raw_token = jwt.encode(payload, "secret-key", algorithm="HS256")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw_token)

    user = await get_current_user(credentials=credentials)
    assert user.is_authenticated is True
    assert user.user_id == "user_2test123"
    assert user.tenant_id == "org_enterprise_99"
    assert user.org_role == "org:admin"
    assert user.org_slug == "acme-corp"


@pytest.mark.asyncio
async def test_bearer_token_personal_workspace_fallback() -> None:
    """Valid JWT without org_id derives personal tenant_id as user_{sub}."""
    payload = {
        "sub": "user_solo_456",
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }
    raw_token = jwt.encode(payload, "secret-key", algorithm="HS256")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw_token)

    user = await get_current_user(credentials=credentials)
    assert user.tenant_id == "user_user_solo_456"
    assert user.org_id is None


def test_expired_token_raises_401() -> None:
    """Expired JWT must raise 401 Unauthorized."""
    expired_payload = {
        "sub": "user_expired",
        "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
    }
    expired_token = jwt.encode(expired_payload, "secret-key", algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        decode_clerk_jwt(expired_token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_rbac_require_role_enforcement() -> None:
    """Admin role permitted, non-admin raises 403 Forbidden."""
    admin_user = AuthenticatedUser(
        user_id="u1", tenant_id="t1", org_role="org:admin", is_authenticated=True
    )
    member_user = AuthenticatedUser(
        user_id="u2", tenant_id="t1", org_role="org:member", is_authenticated=True
    )

    admin_checker = require_role(["admin", "org:admin"])

    # Admin should succeed
    assert admin_checker(admin_user).user_id == "u1"

    # Member should raise 403
    with pytest.raises(HTTPException) as exc_info:
        admin_checker(member_user)
    assert exc_info.value.status_code == 403
