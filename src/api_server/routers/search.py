"""Search endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from common.schemas import Constraint, SearchRequest

router = APIRouter(prefix="/api/v1/search", tags=["search"])


def _get_auth(request: Request):
    return request.app.state.auth


def _get_retrieval(request: Request):
    return request.app.state.retrieval


# ── GET /api/v1/search/test ────────────────────────────────────────────────────

@router.get("/test")
async def search_test(
    request: Request,
    query: str,
    chips: str | None = None,
    debug: bool = False,
) -> Any:
    """Run a search query (viewer+).

    Args:
        query: The search query string.
        chips: Comma-separated chip identifiers for constraint filtering.
        debug: When True, return the full SearchResponse; otherwise only hits.
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
    required_level = auth.ROLE_HIERARCHY.get("viewer", 0)
    user_level = auth.ROLE_HIERARCHY.get(rbac.role, 0)
    if user_level < required_level:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{rbac.role}' insufficient; requires 'viewer' or higher",
        )

    chip_list: list[str] | None = None
    if chips:
        chip_list = [c.strip() for c in chips.split(",") if c.strip()]

    constraint: Constraint | None = None
    if chip_list:
        constraint = Constraint(chip=chip_list)

    search_req = SearchRequest(query=query, constraints=constraint)
    retrieval = _get_retrieval(request)
    response = await retrieval.search(search_req)

    if debug:
        if hasattr(response, "model_dump"):
            return response.model_dump()
        return response
    else:
        if hasattr(response, "hits"):
            return {"hits": response.hits}
        if isinstance(response, dict):
            return {"hits": response.get("hits", [])}
        return {"hits": []}
