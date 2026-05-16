"""Document management REST endpoints."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, status

from api_server.auth import Auth, RBACToken
from common.schemas import DocumentMeta, DocumentStatus

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_auth(request: Request) -> Auth:
    return request.app.state.auth


def _get_doc_dao(request: Request):
    return request.app.state.doc_dao


def _get_pipeline(request: Request):
    return request.app.state.pipeline


def _extract_token(request: Request) -> str:
    """Extract Bearer token from Authorization header or raise 401."""
    authorization: str | None = request.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _check_role(auth: Auth, token: str, min_role: str) -> RBACToken:
    """Verify token and check role >= min_role; raise 401 or 403 as needed."""
    rbac = auth.verify_token(token)
    required_level = auth.ROLE_HIERARCHY.get(min_role, 0)
    user_level = auth.ROLE_HIERARCHY.get(rbac.role, 0)
    if user_level < required_level:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{rbac.role}' insufficient; requires '{min_role}' or higher",
        )
    return rbac


# ── POST /api/v1/documents ─────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile,
    meta: str = Form(...),
) -> dict[str, Any]:
    """Import a single document (importer+)."""
    auth = _get_auth(request)
    token = _extract_token(request)
    _check_role(auth, token, "importer")

    try:
        meta_dict = json.loads(meta)
        doc_meta = DocumentMeta(**meta_dict)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid meta JSON: {exc}",
        ) from exc

    file_data = await file.read()
    pipeline = _get_pipeline(request)
    result = await pipeline.process_document(file_data, file.filename or "upload", doc_meta)

    return {
        "doc_id": result["doc_id"],
        "chunk_count": result["chunk_count"],
        "status": result["status"],
    }


# ── POST /api/v1/documents/batch ───────────────────────────────────────────────

@router.post("/batch")
async def upload_documents_batch(
    request: Request,
    files: list[UploadFile],
    metas: str = Form(...),
) -> list[dict[str, Any]]:
    """Import multiple documents concurrently (importer+)."""
    auth = _get_auth(request)
    token = _extract_token(request)
    _check_role(auth, token, "importer")

    try:
        meta_list = json.loads(metas)
        if not isinstance(meta_list, list):
            raise ValueError("metas must be a JSON array")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid metas JSON: {exc}",
        ) from exc

    if len(files) != len(meta_list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Number of files and metas must match",
        )

    pipeline = _get_pipeline(request)

    async def _process_one(upload: UploadFile, meta_dict: dict) -> dict[str, Any]:
        filename = upload.filename or "upload"
        try:
            doc_meta = DocumentMeta(**meta_dict)
            file_data = await upload.read()
            result = await pipeline.process_document(file_data, filename, doc_meta)
            return {
                "doc_id": result["doc_id"],
                "filename": filename,
                "status": result["status"],
                "error": None,
            }
        except Exception as exc:
            return {
                "doc_id": None,
                "filename": filename,
                "status": "error",
                "error": str(exc),
            }

    tasks = [_process_one(f, m) for f, m in zip(files, meta_list)]
    results = await asyncio.gather(*tasks)
    return list(results)


# ── GET /api/v1/documents ──────────────────────────────────────────────────────

@router.get("")
async def list_documents(
    request: Request,
    status_filter: str | None = None,
    category: str | None = None,
    chip: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List documents with optional filters (viewer+)."""
    auth = _get_auth(request)
    token = _extract_token(request)
    _check_role(auth, token, "viewer")

    doc_dao = _get_doc_dao(request)
    items = await doc_dao.list(
        status=status_filter,
        category=category,
        chip=chip,
        limit=limit,
        offset=offset,
    )
    return {"items": [item.model_dump() for item in items], "total": len(items)}


# ── GET /api/v1/documents/{doc_id} ────────────────────────────────────────────

@router.get("/{doc_id}")
async def get_document(
    request: Request,
    doc_id: str,
) -> dict[str, Any]:
    """Fetch a document by ID (viewer+)."""
    auth = _get_auth(request)
    token = _extract_token(request)
    _check_role(auth, token, "viewer")

    doc_dao = _get_doc_dao(request)
    meta = await doc_dao.get(doc_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return meta.model_dump()


# ── PATCH /api/v1/documents/{doc_id} ──────────────────────────────────────────

@router.patch("/{doc_id}")
async def update_document(
    request: Request,
    doc_id: str,
) -> dict[str, Any]:
    """Update document metadata (importer: own docs only, reviewer+: any)."""
    auth = _get_auth(request)
    token = _extract_token(request)
    rbac = _check_role(auth, token, "importer")

    # importer can only update their own documents; reviewer+ can update any
    reviewer_level = auth.ROLE_HIERARCHY.get("reviewer", 0)
    user_level = auth.ROLE_HIERARCHY.get(rbac.role, 0)
    if user_level < reviewer_level:
        doc_dao = _get_doc_dao(request)
        meta = await doc_dao.get(doc_id)
        if meta is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        if meta.author != rbac.sub:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Importers can only update their own documents",
            )

    body = await request.json()
    updates: dict[str, Any] = {}
    if "status" in body and body["status"] is not None:
        updates["status"] = body["status"]
    if "tags" in body and body["tags"] is not None:
        updates["tags"] = body["tags"]
    if "doc_version" in body and body["doc_version"] is not None:
        updates["doc_version"] = body["doc_version"]

    if updates:
        doc_dao = _get_doc_dao(request)
        await doc_dao.update_meta(doc_id, updates)

    return {"ok": True}


# ── POST /api/v1/documents/{doc_id}/publish ───────────────────────────────────

@router.post("/{doc_id}/publish")
async def publish_document(
    request: Request,
    doc_id: str,
) -> dict[str, Any]:
    """Set document status to published (reviewer+)."""
    auth = _get_auth(request)
    token = _extract_token(request)
    _check_role(auth, token, "reviewer")

    doc_dao = _get_doc_dao(request)
    meta = await doc_dao.get(doc_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await doc_dao.update_meta(doc_id, {"status": DocumentStatus.PUBLISHED.value})
    return {"doc_id": doc_id, "status": "published"}


# ── DELETE /api/v1/documents/{doc_id} ─────────────────────────────────────────

@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    request: Request,
    doc_id: str,
) -> None:
    """Soft-delete a document (admin only)."""
    auth = _get_auth(request)
    token = _extract_token(request)
    _check_role(auth, token, "admin")

    doc_dao = _get_doc_dao(request)
    await doc_dao.soft_delete(doc_id)
