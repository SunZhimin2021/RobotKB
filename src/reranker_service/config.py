from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class RerankerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KB_RERANKER_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Model paths ----
    # Path to the bge-reranker-v2-m3 ONNX model file (.onnx)
    model_path: Path = Path("/models/bge-reranker-v2-m3/model.onnx")

    # Path to tokenizer directory
    tokenizer_path: Path = Path("/models/bge-reranker-v2-m3")

    # ---- Inference backend ----
    execution_provider: str = "CUDAExecutionProvider"

    # ---- Batching ----
    # Each request contains (query, passage) pairs; batch_size = number of pairs
    max_batch_size: int = 8
    max_wait_ms: int = 50
    max_token_length: int = 512

    # ---- Service ----
    host: str = "0.0.0.0"
    port: int = 8002
    workers: int = 1


@lru_cache(maxsize=1)
def get_reranker_settings() -> RerankerSettings:
    return RerankerSettings()
