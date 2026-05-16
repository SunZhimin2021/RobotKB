"""FastAPI application factory for the RobotKB API server."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api_server.auth import Auth
from api_server.routers.compatibility import router as compatibility_router
from api_server.routers.documents import router as documents_router
from api_server.routers.search import router as search_router
from common.exceptions import KBException


def create_app(
    doc_dao,
    pipeline,
    retrieval,
    auth: Auth,
) -> FastAPI:
    """Assemble and return the FastAPI application.

    Args:
        doc_dao:   DocumentDAO instance.
        pipeline:  ETLPipeline instance.
        retrieval: RetrievalEngine (duck-typed).
        auth:      Auth instance for RBAC.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="RobotKB API",
        version="1.0.0",
        description="Document management REST API for RobotKB",
    )

    # ── CORS (development: allow all origins) ─────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Dependency injection via app.state ────────────────────────────────────
    app.state.doc_dao = doc_dao
    app.state.pipeline = pipeline
    app.state.retrieval = retrieval
    app.state.auth = auth

    # ── Global exception handler for KBException ──────────────────────────────
    @app.exception_handler(KBException)
    async def kb_exception_handler(request: Request, exc: KBException) -> JSONResponse:
        # Map internal error codes to HTTP status codes
        code = exc.code
        if 40000 <= code < 40100:
            http_status = 400
        elif code == 40001:
            http_status = 400
        elif code == 40002:
            http_status = 404
        elif code == 40003:
            http_status = 409
        elif 50000 <= code < 50100:
            http_status = 503
        else:
            http_status = 500

        return JSONResponse(
            status_code=http_status,
            content={"detail": str(exc), "code": code},
        )

    # ── Mount routers ─────────────────────────────────────────────────────────
    app.include_router(documents_router)
    app.include_router(search_router)
    app.include_router(compatibility_router)

    return app
