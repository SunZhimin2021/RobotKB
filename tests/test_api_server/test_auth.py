"""Tests for api_server.auth — RBAC JWT authentication."""
from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from api_server.auth import Auth, RBACToken

_SECRET = "test-api-jwt-secret-for-unit-tests"


@pytest.fixture()
def auth() -> Auth:
    return Auth(secret=_SECRET)


# ── test_create_verify_token ───────────────────────────────────────────────────

def test_create_verify_token(auth: Auth) -> None:
    """create_token → verify_token succeeds and returns correct claims."""
    token = auth.create_token("user-123", "reviewer")
    rbac = auth.verify_token(token)

    assert isinstance(rbac, RBACToken)
    assert rbac.sub == "user-123"
    assert rbac.role == "reviewer"
    assert rbac.exp > int(time.time())


# ── test_expired_token_raises ─────────────────────────────────────────────────

def test_expired_token_raises(auth: Auth) -> None:
    """An expired token raises HTTPException 401."""
    token = auth.create_token("user-456", "viewer", expires_in=-1)
    with pytest.raises(HTTPException) as exc_info:
        auth.verify_token(token)
    assert exc_info.value.status_code == 401


# ── test_role_hierarchy ───────────────────────────────────────────────────────

def test_role_hierarchy(auth: Auth) -> None:
    """admin >= reviewer >= importer >= viewer in ROLE_HIERARCHY."""
    h = auth.ROLE_HIERARCHY
    assert h["admin"] > h["reviewer"]
    assert h["reviewer"] > h["importer"]
    assert h["importer"] > h["viewer"]
    assert h["viewer"] >= 1


# ── test_invalid_role_in_require ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_role_in_require(auth: Auth) -> None:
    """A viewer token calling require_role('admin') raises HTTPException 403."""
    token = auth.create_token("viewer-user", "viewer")
    checker = auth.require_role("admin")

    with pytest.raises(HTTPException) as exc_info:
        await checker(token=token)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_role_no_token(auth: Auth) -> None:
    """Missing token in require_role raises HTTPException 401."""
    checker = auth.require_role("viewer")
    with pytest.raises(HTTPException) as exc_info:
        await checker(token=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_role_sufficient(auth: Auth) -> None:
    """reviewer token satisfies require_role('importer')."""
    token = auth.create_token("rev-user", "reviewer")
    checker = auth.require_role("importer")
    rbac = await checker(token=token)
    assert rbac.sub == "rev-user"
    assert rbac.role == "reviewer"
