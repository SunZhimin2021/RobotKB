"""Tests for document management endpoints."""
from __future__ import annotations

import io
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from api_server.auth import Auth
from common.schemas import DocumentMeta, DocumentStatus


def _headers(auth: Auth, role: str, user_id: str = "test-user") -> dict[str, str]:
    token = auth.create_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}


# ── test_upload_document_201 ──────────────────────────────────────────────────

def test_upload_document_201(client: TestClient, auth: Auth, sample_meta: DocumentMeta) -> None:
    """POST /documents with importer token should return 201 with doc_id."""
    headers = _headers(auth, "importer", "user-importer")
    meta_json = sample_meta.model_dump_json()

    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={
            "file": ("test.txt", io.BytesIO(b"hello world"), "text/plain"),
        },
        data={
            "meta": meta_json,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert "doc_id" in body
    assert body["doc_id"] == "doc-abc123"
    assert "chunk_count" in body
    assert "status" in body


# ── test_upload_requires_importer ─────────────────────────────────────────────

def test_upload_requires_importer(client: TestClient, auth: Auth, sample_meta: DocumentMeta) -> None:
    """POST /documents with viewer token should return 403."""
    headers = _headers(auth, "viewer")
    meta_json = sample_meta.model_dump_json()

    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={
            "file": ("test.txt", io.BytesIO(b"hello world"), "text/plain"),
        },
        data={
            "meta": meta_json,
        },
    )
    assert response.status_code == 403, response.text


# ── test_list_documents_viewer ────────────────────────────────────────────────

def test_list_documents_viewer(client: TestClient, auth: Auth) -> None:
    """GET /documents with viewer token should return 200 with items list."""
    headers = _headers(auth, "viewer")
    response = client.get("/api/v1/documents", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)


# ── test_get_document_not_found ───────────────────────────────────────────────

def test_get_document_not_found(
    client: TestClient,
    auth: Auth,
    mock_doc_dao,
) -> None:
    """GET /documents/unknown should return 404."""
    mock_doc_dao.get = AsyncMock(return_value=None)
    headers = _headers(auth, "viewer")
    response = client.get("/api/v1/documents/unknown-id", headers=headers)
    assert response.status_code == 404, response.text


# ── test_publish_requires_reviewer ───────────────────────────────────────────

def test_publish_requires_reviewer(client: TestClient, auth: Auth) -> None:
    """POST /documents/{doc_id}/publish with importer token should return 403."""
    headers = _headers(auth, "importer")
    response = client.post("/api/v1/documents/doc-abc123/publish", headers=headers)
    assert response.status_code == 403, response.text


# ── test_publish_document_ok ──────────────────────────────────────────────────

def test_publish_document_ok(client: TestClient, auth: Auth) -> None:
    """POST /documents/{doc_id}/publish with reviewer token should return 200."""
    headers = _headers(auth, "reviewer")
    response = client.post("/api/v1/documents/doc-abc123/publish", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "published"
    assert body["doc_id"] == "doc-abc123"


# ── Additional tests ──────────────────────────────────────────────────────────

def test_list_documents_no_auth(client: TestClient) -> None:
    """GET /documents without auth should return 401."""
    response = client.get("/api/v1/documents")
    assert response.status_code == 401, response.text


def test_delete_document_admin_only(client: TestClient, auth: Auth) -> None:
    """DELETE /documents/{doc_id} with reviewer token should return 403."""
    headers = _headers(auth, "reviewer")
    response = client.delete("/api/v1/documents/doc-abc123", headers=headers)
    assert response.status_code == 403, response.text


def test_delete_document_admin_ok(client: TestClient, auth: Auth) -> None:
    """DELETE /documents/{doc_id} with admin token should return 204."""
    headers = _headers(auth, "admin")
    response = client.delete("/api/v1/documents/doc-abc123", headers=headers)
    assert response.status_code == 204, response.text


def test_get_document_ok(client: TestClient, auth: Auth) -> None:
    """GET /documents/{doc_id} with viewer token and existing doc returns 200."""
    headers = _headers(auth, "viewer")
    response = client.get("/api/v1/documents/doc-abc123", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Test Document"
