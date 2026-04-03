"""
Retrieval service — the heart of the memory layer.

Algorithm:
  1. Embed the incoming query.
  2. Run pgvector cosine similarity search against memory_embeddings
     filtered to the requesting user.
  3. Re-rank results using a weighted composite score:
       final_score = 0.7 * cosine_similarity
                   + 0.2 * recency_score
                   + 0.1 * importance_score
  4. Filter out results below the similarity threshold.
  5. Return top-k memories with their scores.
  6. For context injection, build an augmented prompt string.
"""

import uuid
import math
from datetime import datetime, timezone
from typing import Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, text

from app.models.memory import Memory, MemoryEmbedding, MemoryStatus, MemoryType
from app.models.user import User
from app.schemas.memory import MemorySearchRequest, MemorySearchResult, ContextRequest, ContextResponse
from app.services.embedding_service import embedding_service
from app.services.encryption_service import decrypt
from app.config import settings

log = structlog.get_logger()

# Scoring weights — must sum to 1.0
W_SIMILARITY = 0.70
W_RECENCY = 0.20
W_IMPORTANCE = 0.10

# Recency half-life in days: a memory accessed 30 days ago scores 0.5
RECENCY_HALF_LIFE_DAYS = 30


def _recency_score(captured_at: datetime) -> float:
    """Exponential decay: score = 0.5^(days_old / half_life)."""
    now = datetime.now(timezone.utc)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    days_old = (now - captured_at).total_seconds() / 86400
    return math.pow(0.5, days_old / RECENCY_HALF_LIFE_DAYS)


class RetrievalService:

    async def search(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        request: MemorySearchRequest,
    ) -> list[MemorySearchResult]:
        """Semantic search over the user's memories."""
        query_embedding = await embedding_service.embed(request.query)
        raw_results = await self._vector_search(
            db,
            user_id=user_id,
            query_embedding=query_embedding,
            limit=request.limit * 3,  # fetch more, re-rank, then truncate
            memory_types=request.memory_types,
            platforms=request.platforms,
        )

        # Re-rank
        scored = []
        salt = await self._get_salt(db, user_id)

        for memory, cosine_sim in raw_results:
            if cosine_sim < request.similarity_threshold:
                continue

            recency = _recency_score(memory.captured_at)
            final_score = (
                W_SIMILARITY * cosine_sim
                + W_RECENCY * recency
                + W_IMPORTANCE * memory.importance_score
            )

            # Decrypt content for the response
            try:
                memory.content = decrypt(memory.content, salt)
                if memory.summary:
                    memory.summary = decrypt(memory.summary, salt)
            except Exception:
                memory.content = "[decryption error]"

            scored.append((memory, final_score))

        # Sort descending by composite score, truncate to requested limit
        scored.sort(key=lambda x: x[1], reverse=True)
        scored = scored[: request.limit]

        return [
            MemorySearchResult(
                memory=memory,
                similarity_score=round(score, 4),
                relevance_rank=rank + 1,
            )
            for rank, (memory, score) in enumerate(scored)
        ]

    async def get_context(
        self,
        db: AsyncSession,
        user: User,
        request: ContextRequest,
    ) -> ContextResponse:
        """
        Given a prompt, retrieve relevant memories and return an augmented prompt
        with injected context.

        Injected context format:
            [MEMORY CONTEXT]
            - <summary or content snippet>
            - <summary or content snippet>
            [END CONTEXT]

            <original prompt>
        """
        search_req = MemorySearchRequest(
            query=request.prompt,
            limit=request.max_memories,
            similarity_threshold=settings.similarity_threshold,
        )
        results = await self.search(db, user.id, search_req)

        if not results:
            return ContextResponse(
                original_prompt=request.prompt,
                augmented_prompt=request.prompt,
                injected_memories=[],
                context_tokens_used=0,
            )

        # Build context block, respecting token budget
        context_lines = []
        tokens_used = 0

        for result in results:
            mem = result.memory
            snippet = mem.summary or mem.content[:300]
            # Truncate long snippets
            line = f"- {snippet.strip()}"
            line_tokens = embedding_service.count_tokens(line)

            if tokens_used + line_tokens > request.max_tokens:
                break

            context_lines.append(line)
            tokens_used += line_tokens

        context_block = "[MEMORY CONTEXT]\n" + "\n".join(context_lines) + "\n[END CONTEXT]"
        augmented = f"{context_block}\n\n{request.prompt}"

        return ContextResponse(
            original_prompt=request.prompt,
            augmented_prompt=augmented,
            injected_memories=results[: len(context_lines)],
            context_tokens_used=tokens_used,
        )

    # ── Internal ───────────────────────────────────────────────────────────────

    async def _vector_search(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        query_embedding: list[float],
        limit: int,
        memory_types: Optional[list[MemoryType]] = None,
        platforms: Optional[list[str]] = None,
    ) -> list[tuple[Memory, float]]:
        """
        Execute pgvector cosine similarity search.
        Returns list of (Memory, similarity_score) tuples.
        """
        # Build the embedding vector literal for pgvector
        vec_literal = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Base conditions
        conditions = [
            MemoryEmbedding.user_id == user_id,
            Memory.status == MemoryStatus.ACTIVE,
        ]
        if memory_types:
            conditions.append(Memory.memory_type.in_(memory_types))
        if platforms:
            conditions.append(Memory.source_platform.in_(platforms))

        stmt = (
            select(
                Memory,
                (1 - MemoryEmbedding.embedding.cosine_distance(vec_literal)).label("cosine_sim"),
            )
            .join(MemoryEmbedding, MemoryEmbedding.memory_id == Memory.id)
            .where(and_(*conditions))
            .order_by(
                MemoryEmbedding.embedding.cosine_distance(vec_literal)
            )
            .limit(limit)
        )

        result = await db.execute(stmt)
        rows = result.all()
        return [(row[0], float(row[1])) for row in rows]

    async def _get_salt(self, db: AsyncSession, user_id: uuid.UUID) -> str:
        from sqlalchemy import select as sa_select
        from app.models.user import User
        result = await db.execute(
            sa_select(User.encryption_salt).where(User.id == user_id)
        )
        return result.scalar_one()


retrieval_service = RetrievalService()
