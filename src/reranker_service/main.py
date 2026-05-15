"""M07 reranker_service — FastAPI entry point.

Endpoints:
  POST /rerank  → RerankResponse
  GET  /health  → {"status": "ok", "model": "bge-reranker-v2-m3"}
"""
import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from reranker_service.config import get_reranker_settings
from reranker_service.model import BgeRerankerModel
from reranker_service.batcher import DynamicRerankerBatcher
from reranker_service.schemas import RerankRequest, RerankResponse

logger = logging.getLogger("robotkb.reranker")

_model: BgeRerankerModel | None = None
_batcher: DynamicRerankerBatcher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model, _batcher
    cfg = get_reranker_settings()

    logger.info("Loading bge-reranker-v2-m3 model", extra={"path": str(cfg.model_path)})
    _model = BgeRerankerModel(
        model_path=cfg.model_path,
        tokenizer_path=cfg.tokenizer_path,
        execution_provider=cfg.execution_provider,
        max_token_length=cfg.max_token_length,
    )
    _model.load()
    _model.warmup()

    _batcher = DynamicRerankerBatcher(
        model=_model,
        max_batch_size=cfg.max_batch_size,
        max_wait_ms=cfg.max_wait_ms,
    )
    await _batcher.start()
    logger.info("reranker_service ready")

    yield

    await _batcher.stop()
    logger.info("reranker_service shutdown")


app = FastAPI(title="RobotKB Reranker Service", version="1.0.0", lifespan=lifespan)


@app.post("/rerank", response_model=RerankResponse)
async def rerank(req: RerankRequest) -> RerankResponse:
    if _batcher is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service not ready")

    t0 = time.perf_counter()
    job = await _batcher.submit(req.query, req.passages, req.top_n)

    try:
        result: dict = await job.future
    except Exception as exc:
        logger.error("Rerank inference failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Inference error: {exc}",
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return RerankResponse(
        scores=result["scores"],
        ranked_indices=result["ranked_indices"],
        elapsed_ms=round(elapsed_ms, 2),
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": "bge-reranker-v2-m3"}


if __name__ == "__main__":
    import uvicorn
    cfg = get_reranker_settings()
    uvicorn.run("reranker_service.main:app", host=cfg.host, port=cfg.port, workers=cfg.workers)
