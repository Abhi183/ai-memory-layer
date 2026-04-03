"""
AI Memory Layer — FastAPI application entry point.
"""

from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.api.v1 import api_router

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", env=settings.environment)
    await init_db()
    log.info("database_ready")
    yield
    log.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Universal persistent memory layer for AI agents",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global error handler ───────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ── Routes ─────────────────────────────────────────────────────────────────────
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.app_version}
