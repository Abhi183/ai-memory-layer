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
from app.schemas.memory import (
    MemorySearchRequest,
    MemorySearchResult,
    ContextRequest,
    ContextResponse,
    ContextExplainResponse,
    MemoryScoreBreakdown,
)
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
        use_adaptive_k: bool = True,
        use_multi_hop: bool = False,
        multi_hop_depth: int = 2,
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

        Args:
            use_adaptive_k:  When True, dynamically pick k via adaptive_k() instead
                             of using request.max_memories as a hard cap.
            use_multi_hop:   When True, run multi-hop retrieval (MSA Memory Interleave).
            multi_hop_depth: Number of hops when use_multi_hop is True.
        """
        # Prefer fields from the request object if they override the parameter defaults.
        _adaptive_k_flag = getattr(request, "use_adaptive_k", use_adaptive_k)
        _multi_hop_flag = getattr(request, "use_multi_hop", use_multi_hop)
        _hop_depth = getattr(request, "multi_hop_depth", multi_hop_depth)

        if _multi_hop_flag:
            from app.services.adaptive_retrieval import multi_hop_retrieve
            scored_pairs = await multi_hop_retrieve(
                db=db,
                user_id=user.id,
                query=request.prompt,
                embedding_service=embedding_service,
                hops=_hop_depth,
                k_per_hop=request.max_memories,
            )
            # Build MemorySearchResult list from (Memory, score) pairs
            results = [
                MemorySearchResult(
                    memory=mem,
                    similarity_score=round(score, 4),
                    relevance_rank=rank + 1,
                )
                for rank, (mem, score) in enumerate(scored_pairs[: request.max_memories * 2])
            ]
        else:
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

        # ── Adaptive-k selection ─────────────────────────────────────────────
        if _adaptive_k_flag:
            from app.services.adaptive_retrieval import adaptive_k
            scores = [r.similarity_score for r in results]
            k = adaptive_k(
                scores,
                min_k=1,
                max_k=request.max_memories,
                threshold=settings.similarity_threshold,
            )
            results = results[:k]

        # ── Build context block, respecting token budget ──────────────────────
        context_lines = []
        tokens_used = 0

        for result in results:
            mem = result.memory
            snippet = mem.summary or mem.content[:300]
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

    async def get_context_explain(
        self,
        db: AsyncSession,
        user: User,
        request: ContextRequest,
    ) -> ContextExplainResponse:
        """
        Debug version of get_context that returns a full score breakdown showing:
          - Per-memory cosine / recency / importance scores
          - Which retrieval hop surfaced each memory
          - Whether adaptive-k was triggered and what k it chose
          - Total T_aug tokens
        """
        _adaptive_k_flag = getattr(request, "use_adaptive_k", True)
        _multi_hop_flag = getattr(request, "use_multi_hop", False)
        _hop_depth = getattr(request, "multi_hop_depth", 2)

        candidate_breakdowns: list[MemoryScoreBreakdown] = []
        hops_executed = 1

        if _multi_hop_flag:
            from app.services.adaptive_retrieval import multi_hop_retrieve
            scored_pairs = await multi_hop_retrieve(
                db=db,
                user_id=user.id,
                query=request.prompt,
                embedding_service=embedding_service,
                hops=_hop_depth,
                k_per_hop=request.max_memories,
            )
            hops_executed = _hop_depth

            # We need raw per-component scores for the breakdown.
            # multi_hop_retrieve returns composite scores; re-derive components
            # from a fresh vector search for transparency.
            hop1_embedding = await embedding_service.embed(request.prompt)
            hop1_raw = await self._vector_search(
                db,
                user_id=user.id,
                query_embedding=hop1_embedding,
                limit=request.max_memories * 3,
            )
            salt = await self._get_salt(db, user.id)
            hop1_ids = set()
            for memory, cosine_sim in hop1_raw:
                recency = _recency_score(memory.captured_at)
                composite = (
                    W_SIMILARITY * cosine_sim
                    + W_RECENCY * recency
                    + W_IMPORTANCE * memory.importance_score
                )
                try:
                    summary = decrypt(memory.summary, salt) if memory.summary else None
                    content = decrypt(memory.content, salt)
                except Exception:
                    summary = None
                    content = "[decryption error]"

                snippet = (summary or content)[:120]
                candidate_breakdowns.append(
                    MemoryScoreBreakdown(
                        memory_id=memory.id,
                        summary_snippet=snippet,
                        cosine_score=round(cosine_sim, 4),
                        recency_score=round(recency, 4),
                        importance_score=round(memory.importance_score, 4),
                        composite_score=round(composite, 4),
                        hop=1,
                    )
                )
                hop1_ids.add(memory.id)

            # Mark hop-2 memories
            for mem, score in scored_pairs:
                if mem.id not in hop1_ids:
                    # Approximate cosine from composite (we don't have raw value here)
                    candidate_breakdowns.append(
                        MemoryScoreBreakdown(
                            memory_id=mem.id,
                            summary_snippet=(mem.summary or mem.content)[:120],
                            cosine_score=round(score, 4),  # best approximation
                            recency_score=round(_recency_score(mem.captured_at), 4),
                            importance_score=round(mem.importance_score, 4),
                            composite_score=round(score, 4),
                            hop=2,
                        )
                    )

            results = [
                MemorySearchResult(
                    memory=mem,
                    similarity_score=round(score, 4),
                    relevance_rank=rank + 1,
                )
                for rank, (mem, score) in enumerate(scored_pairs[: request.max_memories * 2])
            ]
        else:
            # Single-hop path — collect full score breakdown
            query_embedding = await embedding_service.embed(request.prompt)
            raw_results = await self._vector_search(
                db,
                user_id=user.id,
                query_embedding=query_embedding,
                limit=request.max_memories * 3,
            )
            salt = await self._get_salt(db, user.id)

            scored = []
            for memory, cosine_sim in raw_results:
                if cosine_sim < settings.similarity_threshold:
                    continue

                recency = _recency_score(memory.captured_at)
                composite = (
                    W_SIMILARITY * cosine_sim
                    + W_RECENCY * recency
                    + W_IMPORTANCE * memory.importance_score
                )

                try:
                    memory.content = decrypt(memory.content, salt)
                    if memory.summary:
                        memory.summary = decrypt(memory.summary, salt)
                except Exception:
                    memory.content = "[decryption error]"

                snippet = (memory.summary or memory.content)[:120]
                candidate_breakdowns.append(
                    MemoryScoreBreakdown(
                        memory_id=memory.id,
                        summary_snippet=snippet,
                        cosine_score=round(cosine_sim, 4),
                        recency_score=round(recency, 4),
                        importance_score=round(memory.importance_score, 4),
                        composite_score=round(composite, 4),
                        hop=1,
                    )
                )
                scored.append((memory, composite))

            scored.sort(key=lambda x: x[1], reverse=True)
            scored = scored[: request.max_memories]

            results = [
                MemorySearchResult(
                    memory=mem,
                    similarity_score=round(score, 4),
                    relevance_rank=rank + 1,
                )
                for rank, (mem, score) in enumerate(scored)
            ]

        # ── Adaptive-k ───────────────────────────────────────────────────────
        adaptive_k_chosen: Optional[int] = None
        if _adaptive_k_flag and results:
            from app.services.adaptive_retrieval import adaptive_k as _adaptive_k_fn
            scores = [r.similarity_score for r in results]
            adaptive_k_chosen = _adaptive_k_fn(
                scores,
                min_k=1,
                max_k=request.max_memories,
                threshold=settings.similarity_threshold,
            )
            results = results[:adaptive_k_chosen]

        # ── Token budget ─────────────────────────────────────────────────────
        context_lines = []
        tokens_used = 0
        for result in results:
            mem = result.memory
            snippet = mem.summary or mem.content[:300]
            line = f"- {snippet.strip()}"
            line_tokens = embedding_service.count_tokens(line)
            if tokens_used + line_tokens > request.max_tokens:
                break
            context_lines.append(line)
            tokens_used += line_tokens

        if context_lines:
            context_block = "[MEMORY CONTEXT]\n" + "\n".join(context_lines) + "\n[END CONTEXT]"
            augmented = f"{context_block}\n\n{request.prompt}"
        else:
            augmented = request.prompt

        # Sort breakdowns by composite score for readability
        candidate_breakdowns.sort(key=lambda x: x.composite_score, reverse=True)

        return ContextExplainResponse(
            original_prompt=request.prompt,
            candidate_scores=candidate_breakdowns,
            injected_memories=results[: len(context_lines)],
            adaptive_k_used=_adaptive_k_flag,
            adaptive_k_chosen=adaptive_k_chosen,
            multi_hop_used=_multi_hop_flag,
            hops_executed=hops_executed,
            context_tokens_used=tokens_used,
            augmented_prompt=augmented,
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
