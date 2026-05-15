import os
import pytest
from common.config import Settings, get_settings


def make_env(**overrides):
    """Return a minimal valid env dict plus any overrides."""
    base = {
        "KB_PG_DSN": "postgresql+asyncpg://user:pass@localhost:5432/robotkb",
        "KB_MEILI_URL": "http://localhost:7700",
        "KB_NEO4J_URI": "bolt://localhost:7687",
        "KB_MINIO_ENDPOINT": "localhost:9000",
        "KB_MINIO_ACCESS_KEY": "minioadmin",
        "KB_MINIO_SECRET_KEY": "minioadmin",
        "KB_EMBEDDING_URL": "http://localhost:8001",
        "KB_RERANKER_URL": "http://localhost:8002",
        "KB_MCP_TOKEN_SECRET": "test-mcp-secret",
        "KB_API_JWT_SECRET": "test-jwt-secret",
    }
    base.update(overrides)
    return base


def test_settings_loads_required_fields(monkeypatch):
    for k, v in make_env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.pg_dsn == "postgresql+asyncpg://user:pass@localhost:5432/robotkb"
    assert s.meili_url == "http://localhost:7700"
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.minio_endpoint == "localhost:9000"
    assert s.embedding_url == "http://localhost:8001"
    assert s.reranker_url == "http://localhost:8002"


def test_settings_default_values(monkeypatch):
    for k, v in make_env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.rrf_k == 60
    assert s.retrieval_recall == 20
    assert s.rerank_top_n == 10


def test_settings_override_defaults(monkeypatch):
    env = make_env(KB_RRF_K="30", KB_RETRIEVAL_RECALL="15", KB_RERANK_TOP_N="5")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.rrf_k == 30
    assert s.retrieval_recall == 15
    assert s.rerank_top_n == 5


def test_settings_jwt_secrets(monkeypatch):
    for k, v in make_env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.mcp_token_secret == "test-mcp-secret"
    assert s.api_jwt_secret == "test-jwt-secret"


def test_settings_minio_fields(monkeypatch):
    env = make_env(
        KB_MINIO_BUCKET="robotkb-docs",
        KB_MINIO_USE_SSL="true",
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.minio_bucket == "robotkb-docs"
    assert s.minio_use_ssl is True


def test_settings_minio_default_bucket(monkeypatch):
    for k, v in make_env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.minio_bucket == "robotkb"
    assert s.minio_use_ssl is False


def test_settings_missing_required_field_raises(monkeypatch):
    env = make_env()
    del env["KB_PG_DSN"]
    # Clear any existing env var
    monkeypatch.delenv("KB_PG_DSN", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(Exception):
        Settings()


def test_get_settings_returns_singleton(monkeypatch):
    for k, v in make_env().items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    get_settings.cache_clear()


def test_neo4j_auth_fields(monkeypatch):
    env = make_env(KB_NEO4J_USER="neo4j", KB_NEO4J_PASSWORD="password")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.neo4j_user == "neo4j"
    assert s.neo4j_password == "password"
