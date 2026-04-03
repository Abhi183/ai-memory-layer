import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.auth import router as auth_router
from app.api.v1.memory import router as memory_router


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def api_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(memory_router, prefix="/api/v1")
    return app


@pytest.fixture
def client(api_app: FastAPI) -> TestClient:
    return TestClient(api_app)
