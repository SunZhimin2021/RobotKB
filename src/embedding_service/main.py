"""M06 embedding_service — FastAPI entry point.

Endpoints:
  POST /embed   → EmbedResponse
  GET  /health  → {"status": "ok", "model": "bge-m3"}
"""
import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from embedding_service.config import get_embedding_settings
from embedding_service.model import BgeM3Model
from embedding_service.batcher import DynamicBatcher
from embedding_service.schemas import EmbedRequest, EmbedResponse

logger = logging.getLogger("robotkb.embedding")

# Module-level singletons (initialised in lifespan)
_model: BgeM3Model | None = None
_batcher: DynamicBatcher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model, _batcher
    cfg = get_embedding_settings()

    logger.info("Loading bge-m3 model", extra={"path": str(cfg.model_path)})
    _model = BgeM3Model(
        model_path=cfg.model_path,
        tokenizer_path=cfg.tokenizer_path,
        execution_provider=cfg.execution_provider,
        max_token_length=cfg.max_token_length,
        embedding_dim=cfg.embedding_dim,
    )
    _model.load()
    _model.warmup()

    _batcher = DynamicBatcher(
        model=_model,
        max_batch_size=cfg.max_batch_size,
        max_wait_ms=cfg.max_wait_ms,
    )
    await _batcher.start()
    logger.info("embedding_service ready")

    yield

    await _batcher.stop()
    logger.info("embedding_service shutdown")


app = FastAPI(title="RobotKB Embedding Service", version="1.0.0", lifespan=lifespan)


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest) -> EmbedResponse:
    if _batcher is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service not ready")

    t0 = time.perf_counter()
    job = await _batcher.submit(req.texts, req.type)

    try:
        result: dict = await job.future
    except Exception as exc:
        logger.error("Inference failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Inference error: {exc}",
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return EmbedResponse(
        dense=result.get("dense"),
        sparse=result.get("sparse"),
        elapsed_ms=round(elapsed_ms, 2),
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": "bge-m3"}


if __name__ == "__main__":
    import uvicorn
    cfg = get_embedding_settings()
    uvicorn.run("embedding_service.main:app", host=cfg.host, port=cfg.port, workers=cfg.workers)
