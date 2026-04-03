from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import uuid

import pytest

from app.schemas.memory import ContextRequest, MemorySearchResult
from app.services import retrieval_service as retrieval_module
from app.services.retrieval_service import RECENCY_HALF_LIFE_DAYS, RetrievalService, _recency_score


def _search_result(summary: str, rank: int) -> MemorySearchResult:
    memory_payload = {
        "id": uuid.uuid4(),
        "content": f"{summary} content",
        "summary": summary,
        "extracted_facts": {"facts": []},
        "memory_type": "short_term",
        "status": "active",
        "source_platform": "chatgpt",
        "importance_score": 0.5,
        "access_count": 0,
        "tags": [],
        "source": None,
        "captured_at": datetime.now(timezone.utc),
        "processed_at": datetime.now(timezone.utc),
    }
    return MemorySearchResult.model_validate(
        {"memory": memory_payload, "similarity_score": 0.9, "relevance_rank": rank}
    )


@pytest.mark.parametrize(
    "days_old_a,days_old_b",
    [(0, 7), (7, 30), (30, 90)],
)
def test_recency_score_decays(days_old_a, days_old_b):
    now = datetime.now(timezone.utc)
    score_a = _recency_score(now - timedelta(days=days_old_a))
    score_b = _recency_score(now - timedelta(days=days_old_b))
    assert score_a > score_b


def test_recency_score_half_life_behavior():
    now = datetime.now(timezone.utc)
    recent = _recency_score(now)
    half_life = _recency_score(now - timedelta(days=RECENCY_HALF_LIFE_DAYS))
    assert recent == pytest.approx(1.0, rel=1e-2)
    assert half_life == pytest.approx(0.5, rel=1e-1)


@pytest.mark.asyncio
async def test_get_context_returns_original_prompt_when_no_results(monkeypatch):
    service = RetrievalService()
    monkeypatch.setattr(service, "search", AsyncMock(return_value=[]))

    request = ContextRequest(prompt="draft a reply", max_tokens=100, max_memories=3)
    response = await service.get_context(db=AsyncMock(), user=AsyncMock(id="u-1"), request=request)

    assert response.augmented_prompt == request.prompt
    assert response.context_tokens_used == 0
    assert response.injected_memories == []


@pytest.mark.asyncio
async def test_get_context_respects_token_budget(monkeypatch):
    service = RetrievalService()

    search_results = [_search_result("first summary", 1), _search_result("second summary", 2)]

    monkeypatch.setattr(service, "search", AsyncMock(return_value=search_results))
    monkeypatch.setattr(retrieval_module.embedding_service, "count_tokens", lambda _: 10)

    request = ContextRequest(prompt="help me", max_tokens=10, max_memories=5)
    response = await service.get_context(db=AsyncMock(), user=AsyncMock(id="u"), request=request)

    assert "[MEMORY CONTEXT]" in response.augmented_prompt
    assert len(response.injected_memories) == 1
    assert response.context_tokens_used == 10
