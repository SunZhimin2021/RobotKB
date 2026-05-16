"""Shared fixtures for api_server tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api_server.auth import Auth
from api_server.main import create_app
from common.schemas import (
    DocumentCategory,
    DocumentMeta,
    DocumentStatus,
    SearchResponse,
    SourceTier,
)

_SECRET = "test-api-jwt-secret-for-unit-tests"


@pytest.fixture()
def auth() -> Auth:
    return Auth(secret=_SECRET)


@pytest.fixture()
def sample_meta() -> DocumentMeta:
    return DocumentMeta(
        title="Test Document",
        category=DocumentCategory.SOFTWARE,
        source_tier=SourceTier.OFFICIAL,
        applicable_chips=["jetson-orin"],
        applicable_boards=["devkit"],
        ros_versions=["humble"],
        tags=["test"],
        status=DocumentStatus.PENDING,
        author="user-importer",
    )


@pytest.fixture()
def mock_doc_dao(sample_meta: DocumentMeta) -> MagicMock:
    dao = MagicMock()
    dao.create = AsyncMock(return_value="doc-abc123")
    dao.get = AsyncMock(return_value=sample_meta)
    dao.update_meta = AsyncMock(return_value=None)
    dao.list = AsyncMock(return_value=[sample_meta])
    dao.find_by_hash = AsyncMock(return_value=None)
    dao.soft_delete = AsyncMock(return_value=None)
    return dao


@pytest.fixture()
def mock_pipeline() -> MagicMock:
    pipeline = MagicMock()
    pipeline.process_document = AsyncMock(return_value={
        "doc_id": "doc-abc123",
        "chunk_count": 5,
        "status": "pending",
        "ner_result": {"consistent": True},
        "superseded": None,
    })
    return pipeline


@pytest.fixture()
def mock_retrieval() -> MagicMock:
    retrieval = MagicMock()
    retrieval.search = AsyncMock(return_value=SearchResponse(
        query="test query",
        hits=[{"chunk_id": "c1", "content": "relevant content", "score": 0.95}],
    ))
    return retrieval


@pytest.fixture()
def client(auth: Auth, mock_doc_dao, mock_pipeline, mock_retrieval) -> TestClient:
    app = create_app(
        doc_dao=mock_doc_dao,
        pipeline=mock_pipeline,
        retrieval=mock_retrieval,
        auth=auth,
    )
    return TestClient(app, raise_server_exceptions=True)


def make_token(auth: Auth, role: str, user_id: str = "test-user") -> str:
    return auth.create_token(user_id, role)


def auth_headers(auth: Auth, role: str, user_id: str = "test-user") -> dict[str, str]:
    token = make_token(auth, role, user_id)
    return {"Authorization": f"Bearer {token}"}


# Expose as a pytest fixture for convenience
@pytest.fixture()
def make_auth_headers(auth: Auth):
    """Return a callable: make_auth_headers(role, user_id) -> dict."""
    def _make(role: str, user_id: str = "test-user") -> dict[str, str]:
        return auth_headers(auth, role, user_id)
    return _make
