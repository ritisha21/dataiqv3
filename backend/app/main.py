from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
import uuid
import time

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimitMiddleware
from app.db.database import create_tables

from app.api.v1.endpoints import (
    auth,
    connections,
    query,
    chat,          # <-- ADDED
    models,
    dashboard,
    etl,
    export,
)

configure_logging()
logger = structlog.get_logger()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
        redoc_url=None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "https://app.dataiq.io",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting
    app.add_middleware(
        RateLimitMiddleware,
        redis_url=settings.REDIS_URL,
    )

    # Request logging middleware
    @app.middleware("http")
    async def request_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id
        )

        start = time.time()

        try:
            response = await call_next(request)

            elapsed = round(
                (time.time() - start) * 1000,
                2,
            )

            logger.info(
                "request_complete",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                elapsed_ms=elapsed,
            )

            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            elapsed = round(
                (time.time() - start) * 1000,
                2,
            )

            logger.error(
                "request_failed",
                path=request.url.path,
                error=str(e),
                elapsed_ms=elapsed,
            )

            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                },
            )

    # Routers
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(connections.router, prefix="/api/v1")
    app.include_router(query.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")      # <-- ADDED
    app.include_router(models.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    app.include_router(etl.router, prefix="/api/v1")
    app.include_router(export.router, prefix="/api/v1")

    @app.on_event("startup")
    async def startup():
        await create_tables()
        logger.info(
            "app_startup",
            environment=settings.ENVIRONMENT,
        )

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "version": settings.VERSION,
        }

    return app


app = create_app()