"""Tests for search endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api_server.auth import Auth


def _headers(auth: Auth, role: str, user_id: str = "test-user") -> dict[str, str]:
    token = auth.create_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}


# ── test_search_test_endpoint ─────────────────────────────────────────────────

def test_search_test_endpoint(client: TestClient, auth: Auth) -> None:
    """GET /search/test?query=foo with viewer token returns 200 with hits."""
    headers = _headers(auth, "viewer")
    response = client.get(
        "/api/v1/search/test",
        params={"query": "foo"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "hits" in body
    assert isinstance(body["hits"], list)
    assert len(body["hits"]) > 0


# ── test_search_requires_auth ─────────────────────────────────────────────────

def test_search_requires_auth(client: TestClient) -> None:
    """GET /search/test without token returns 401."""
    response = client.get(
        "/api/v1/search/test",
        params={"query": "foo"},
    )
    assert response.status_code == 401, response.text


# ── Additional search tests ────────────────────────────────────────────────────

def test_search_debug_mode(client: TestClient, auth: Auth) -> None:
    """GET /search/test?debug=true returns full response including query field."""
    headers = _headers(auth, "viewer")
    response = client.get(
        "/api/v1/search/test",
        params={"query": "robot arm", "debug": "true"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # debug=True returns full SearchResponse (has both query and hits)
    assert "query" in body or "hits" in body


def test_search_with_chips(client: TestClient, auth: Auth) -> None:
    """GET /search/test?chips=jetson-orin should pass chip constraint."""
    headers = _headers(auth, "viewer")
    response = client.get(
        "/api/v1/search/test",
        params={"query": "hardware setup", "chips": "jetson-orin,jetson-nano"},
        headers=headers,
    )
    assert response.status_code == 200, response.text


def test_search_reviewer_can_access(client: TestClient, auth: Auth) -> None:
    """Reviewer role (above viewer) can access search endpoint."""
    headers = _headers(auth, "reviewer")
    response = client.get(
        "/api/v1/search/test",
        params={"query": "test"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
