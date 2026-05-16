"""Compatibility matrix endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/api/v1/compatibility", tags=["compatibility"])

# In-memory compatibility matrix: { (chip_id, board_id): {"compatible": bool, "note": str|None} }
_matrix: dict[tuple[str, str], dict[str, Any]] = {}


def _get_auth(request: Request):
    return request.app.state.auth


# ── GET /api/v1/compatibility/matrix ──────────────────────────────────────────

@router.get("/matrix")
async def get_matrix(request: Request) -> dict[str, Any]:
    """Return the in-memory compatibility matrix (admin only)."""
    auth = _get_auth(request)
    authorization: str | None = request.headers.get("Authorization")
    token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    rbac = auth.verify_token(token)
    required_level = auth.ROLE_HIERARCHY.get("admin", 0)
    user_level = auth.ROLE_HIERARCHY.get(rbac.role, 0)
    if user_level < required_level:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{rbac.role}' insufficient; requires 'admin'",
        )

    # Serialize tuple keys to string
    serialized = {
        f"{chip}::{board}": entry
        for (chip, board), entry in _matrix.items()
    }
    return serialized


# ── PUT /api/v1/compatibility/matrix ──────────────────────────────────────────

@router.put("/matrix")
async def update_matrix(
    request: Request,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Update compatibility matrix entry (admin only).

    Body: {"chip_id": str, "board_id": str, "compatible": bool, "note": str|None}
    dry_run=True: return preview without modifying the matrix.
    """
    auth = _get_auth(request)
    authorization: str | None = request.headers.get("Authorization")
    token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    rbac = auth.verify_token(token)
    required_level = auth.ROLE_HIERARCHY.get("admin", 0)
    user_level = auth.ROLE_HIERARCHY.get(rbac.role, 0)
    if user_level < required_level:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{rbac.role}' insufficient; requires 'admin'",
        )

    body = await request.json()
    chip_id = body.get("chip_id")
    board_id = body.get("board_id")
    compatible = body.get("compatible")
    note = body.get("note")

    if chip_id is None or board_id is None or compatible is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="chip_id, board_id, and compatible are required",
        )

    key = (chip_id, board_id)
    existing = _matrix.get(key)
    preview = {
        "chip_id": chip_id,
        "board_id": board_id,
        "compatible": compatible,
        "note": note,
        "previous": existing,
    }

    if dry_run:
        return {"dry_run": True, "preview": preview}

    _matrix[key] = {"compatible": compatible, "note": note}
    return {"ok": True}
