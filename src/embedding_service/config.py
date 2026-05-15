from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KB_EMBEDDING_",
        case_sensitive=False,
        # Also loads from .env file if present
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Model paths (set these before starting the service) ----
    # Path to the bge-m3 ONNX model file (.onnx)
    model_path: Path = Path("/models/bge-m3/model.onnx")

    # Path to the tokenizer directory (contains tokenizer.json, config.json, etc.)
    tokenizer_path: Path = Path("/models/bge-m3")

    # ---- Inference backend ----
    # "CUDAExecutionProvider" on Jetson, "CPUExecutionProvider" for local dev
    execution_provider: str = "CUDAExecutionProvider"

    # ---- Batching ----
    max_batch_size: int = 16
    max_wait_ms: int = 50          # max time to accumulate a batch before flushing
    max_token_length: int = 512

    # ---- Dense embedding ----
    embedding_dim: int = 1024      # bge-m3 dense output dimension

    # ---- Service ----
    host: str = "0.0.0.0"
    port: int = 8001
    workers: int = 1               # keep 1 — GPU semaphore controls concurrency


@lru_cache(maxsize=1)
def get_embedding_settings() -> EmbeddingSettings:
    return EmbeddingSettings()
