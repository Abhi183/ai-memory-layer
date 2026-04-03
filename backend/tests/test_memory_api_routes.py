import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.api.v1 import memory as memory_api
from app.middleware.auth import get_current_user
from app.database import get_db
from app.models.memory import MemoryStatus, MemoryType


def _memory_payload(memory_id: uuid.UUID) -> dict:
    return {
        "id": str(memory_id),
        "content": "decrypted content",
        "summary": "short summary",
        "extracted_facts": {"facts": ["fact-1"]},
        "memory_type": MemoryType.SHORT_TERM.value,
        "status": MemoryStatus.ACTIVE.value,
        "source_platform": "chatgpt",
        "importance_score": 0.8,
        "access_count": 2,
        "tags": [],
        "source": None,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def test_memory_crud_and_search_routes(client, api_app):
    user = SimpleNamespace(id=uuid.uuid4(), is_active=True)

    async def override_get_current_user():
        return user

    async def override_get_db():
        yield AsyncMock()

    api_app.dependency_overrides[get_current_user] = override_get_current_user
    api_app.dependency_overrides[get_db] = override_get_db

    memory_id = uuid.uuid4()
    memory_data = _memory_payload(memory_id)

    memory_api.memory_service.capture = AsyncMock(return_value=memory_data)
    memory_api.memory_service.create = AsyncMock(return_value=memory_data)
    memory_api.memory_service.list_memories = AsyncMock(return_value=[memory_data])
    memory_api.memory_service.get = AsyncMock(return_value=memory_data)
    memory_api.memory_service.update = AsyncMock(return_value=memory_data)
    memory_api.memory_service.delete = AsyncMock(return_value=True)
    memory_api.retrieval_service.search = AsyncMock(
        return_value=[{"memory": memory_data, "similarity_score": 0.95, "relevance_rank": 1}]
    )
    memory_api.retrieval_service.get_context = AsyncMock(
        return_value={
            "original_prompt": "hello",
            "augmented_prompt": "[MEMORY CONTEXT]\n- short summary\n[END CONTEXT]\n\nhello",
            "injected_memories": [
                {"memory": memory_data, "similarity_score": 0.95, "relevance_rank": 1}
            ],
            "context_tokens_used": 8,
        }
    )

    capture_response = client.post(
        "/api/v1/memory/capture",
        json={"prompt": "p", "response": "r", "platform": "chatgpt", "tags": []},
    )
    assert capture_response.status_code == 202

    create_response = client.post(
        "/api/v1/memory/",
        json={"content": "hello", "memory_type": "short_term", "tags": []},
    )
    assert create_response.status_code == 201

    list_response = client.get("/api/v1/memory/")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = client.get(f"/api/v1/memory/{memory_id}")
    assert get_response.status_code == 200

    patch_response = client.patch(
        f"/api/v1/memory/{memory_id}", json={"summary": "updated"}
    )
    assert patch_response.status_code == 200

    search_response = client.get("/api/v1/memory/search", params={"q": "find", "limit": 5})
    assert search_response.status_code == 200
    assert search_response.json()[0]["relevance_rank"] == 1

    context_response = client.post(
        "/api/v1/memory/context",
        json={"prompt": "hello", "max_tokens": 100, "max_memories": 3},
    )
    assert context_response.status_code == 200
    assert "MEMORY CONTEXT" in context_response.json()["augmented_prompt"]

    delete_response = client.delete(f"/api/v1/memory/{memory_id}")
    assert delete_response.status_code == 204


def test_memory_get_not_found_returns_404(client, api_app):
    user = SimpleNamespace(id=uuid.uuid4(), is_active=True)

    async def override_get_current_user():
        return user

    async def override_get_db():
        yield AsyncMock()

    api_app.dependency_overrides[get_current_user] = override_get_current_user
    api_app.dependency_overrides[get_db] = override_get_db

    memory_api.memory_service.get = AsyncMock(return_value=None)

    response = client.get(f"/api/v1/memory/{uuid.uuid4()}")
    assert response.status_code == 404
