from app.services.embedding_service import EmbeddingService
from app.config import settings


def test_count_tokens_non_empty_text():
    service = EmbeddingService()
    assert service.count_tokens("hello world") > 0


def test_chunk_text_respects_small_chunk_size(monkeypatch):
    service = EmbeddingService()
    monkeypatch.setattr(settings, "max_chunk_size", 12)
    monkeypatch.setattr(settings, "chunk_overlap", 3)

    text = (
        "Sentence one has several words. "
        "Sentence two also has several words. "
        "Sentence three is here too."
    )
    chunks = service.chunk_text(text)

    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)


def test_dimensions_switches_with_local_embeddings(monkeypatch):
    service = EmbeddingService()

    monkeypatch.setattr(settings, "use_local_embeddings", False)
    assert service.dimensions == settings.embedding_dimensions

    monkeypatch.setattr(settings, "use_local_embeddings", True)
    assert service.dimensions == settings.local_embedding_dimensions
