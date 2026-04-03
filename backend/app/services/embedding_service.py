"""
Embedding service with two backends:
  1. OpenAI text-embedding-3-small (default, best quality)
  2. sentence-transformers all-MiniLM-L6-v2 (local fallback, no API key needed)

Chunking strategy:
  - Split on sentence boundaries first, then respect max_chunk_size tokens.
  - Overlap chunks by `chunk_overlap` tokens to preserve cross-boundary context.
  - Store each chunk as a separate embedding, linked to the parent memory.
"""

import asyncio
import hashlib
from typing import Optional
import tiktoken
import structlog

from app.config import settings

log = structlog.get_logger()


class EmbeddingService:
    def __init__(self):
        self._openai_client: Optional[object] = None
        self._local_model: Optional[object] = None
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

    def _get_openai_client(self):
        if self._openai_client is None:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    def _get_local_model(self):
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer(settings.local_embedding_model)
        return self._local_model

    def count_tokens(self, text: str) -> int:
        return len(self._tokenizer.encode(text))

    def chunk_text(self, text: str) -> list[str]:
        """
        Split text into overlapping chunks respecting token limits.

        Strategy:
          1. Split into sentences (simple period/newline heuristic).
          2. Greedily fill chunks up to max_chunk_size.
          3. When a chunk is full, start the next one with the last
             `chunk_overlap` tokens of the current chunk.
        """
        max_size = settings.max_chunk_size
        overlap = settings.chunk_overlap

        # Sentence-level split
        import re
        sentences = re.split(r'(?<=[.!?])\s+|\n\n+', text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks: list[str] = []
        current_tokens: list[int] = []
        current_sentences: list[str] = []

        for sentence in sentences:
            sent_tokens = self._tokenizer.encode(sentence)
            if len(current_tokens) + len(sent_tokens) > max_size and current_sentences:
                chunks.append(" ".join(current_sentences))
                # Overlap: keep trailing tokens to reconstruct overlap sentences
                overlap_text = self._tokenizer.decode(current_tokens[-overlap:])
                current_sentences = [overlap_text, sentence]
                current_tokens = self._tokenizer.encode(overlap_text) + sent_tokens
            else:
                current_sentences.append(sentence)
                current_tokens.extend(sent_tokens)

        if current_sentences:
            chunks.append(" ".join(current_sentences))

        return chunks if chunks else [text[:2000]]  # hard fallback

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string, returning the embedding vector."""
        if settings.use_local_embeddings or not settings.openai_api_key:
            return await self._embed_local(text)
        return await self._embed_openai(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single API call (more efficient)."""
        if settings.use_local_embeddings or not settings.openai_api_key:
            return await asyncio.gather(*[self._embed_local(t) for t in texts])
        return await self._embed_openai_batch(texts)

    async def _embed_openai(self, text: str) -> list[float]:
        client = self._get_openai_client()
        response = await client.embeddings.create(
            input=[text],
            model=settings.openai_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        return response.data[0].embedding

    async def _embed_openai_batch(self, texts: list[str]) -> list[list[float]]:
        client = self._get_openai_client()
        response = await client.embeddings.create(
            input=texts,
            model=settings.openai_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        # API returns embeddings in the same order as inputs
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

    async def _embed_local(self, text: str) -> list[float]:
        model = self._get_local_model()
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(None, model.encode, text)
        return embedding.tolist()

    @property
    def dimensions(self) -> int:
        if settings.use_local_embeddings:
            return settings.local_embedding_dimensions
        return settings.embedding_dimensions


embedding_service = EmbeddingService()
