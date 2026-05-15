from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KB_", case_sensitive=False)

    # PostgreSQL + pgvector
    pg_dsn: str

    # Meilisearch
    meili_url: str
    meili_api_key: str = ""

    # Neo4j
    neo4j_uri: str
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"

    # MinIO
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str = "robotkb"
    minio_use_ssl: bool = False

    # Inference service URLs (OpenAI-compatible, deployed on Jetson 192.168.3.58)
    # embedding: POST {embedding_url}/v1/embeddings
    # reranker:  POST {reranker_url}/v1/rerank
    embedding_url: str = "http://192.168.3.58:7997"
    embedding_model: str = "bge-m3"
    reranker_url: str = "http://192.168.3.58:7998"
    reranker_model: str = "bge-reranker-v2-m3"

    # Retrieval tuning
    rrf_k: int = 60
    retrieval_recall: int = 20
    rerank_top_n: int = 10

    # Auth
    mcp_token_secret: str
    api_jwt_secret: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
