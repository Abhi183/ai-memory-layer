"""
Adaptive retrieval utilities inspired by MSA (Memory Sparse Attention).

Three main capabilities:
  1. adaptive_k          — select how many memories to inject based on score gaps,
                           mirroring MSA's top-k routing that adapts to score distribution.
  2. compress_memory_group — chunk-mean-style compression: collapse a group of related
                           memory summaries into a single injected line, reducing T_aug.
  3. multi_hop_retrieve  — two-pass retrieval: initial query → retrieved memories become
                           secondary queries, bridging to related memories the first hop
                           would miss (mirrors MSA Memory Interleave).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.memory import Memory
    from app.services.embedding_service import EmbeddingService

log = structlog.get_logger()


# ── 1. Adaptive Top-k Selection ───────────────────────────────────────────────


def adaptive_k(
    scores: list[float],
    min_k: int = 1,
    max_k: int = 10,
    threshold: float = 0.65,
    margin: float = 0.15,
) -> int:
    """
    Determine how many memories to inject based on score distribution.

    Algorithm:
      - Sort scores descending (caller is expected to pass already-sorted scores,
        but we re-sort defensively).
      - Always include memories whose composite score exceeds `threshold`.
      - Stop when the score gap between consecutive memories exceeds `margin`
        (a sharp drop-off signals we've left the relevant cluster).
      - Clamp the result between min_k and max_k.

    This mirrors MSA's adaptive routing: a document is included only when its
    routing score exceeds the top-k mean by less than `margin`, keeping injection
    tight around the truly relevant set rather than padding with marginal results.

    Args:
        scores:    Composite scores for each candidate memory, in any order.
        min_k:     Minimum memories to return even if scores are low.
        max_k:     Hard ceiling on the number of memories returned.
        threshold: Composite score below which a memory is excluded.
        margin:    Maximum tolerated drop between adjacent scores before stopping.

    Returns:
        The number of top memories to use (1 ≤ result ≤ max_k).

    Example:
        >>> scores = [0.91, 0.88, 0.85, 0.60, 0.55]
        >>> adaptive_k(scores, threshold=0.65, margin=0.15)
        3   # stops after 0.85 because the next drop (0.85→0.60) is 0.25 > margin
    """
    if not scores:
        return min_k

    sorted_scores = sorted(scores, reverse=True)

    chosen = 0
    for i, score in enumerate(sorted_scores):
        if i >= max_k:
            break

        # Hard threshold: always include if above threshold
        if score >= threshold:
            chosen = i + 1
            continue

        # Below threshold: stop immediately (no point continuing)
        break

    # Now apply margin rule: walk back from chosen and check consecutive gaps.
    # If there's a sharp drop earlier, tighten the selection.
    refined = 0
    for i in range(min(chosen, len(sorted_scores))):
        if i == 0:
            refined = 1
            continue
        gap = sorted_scores[i - 1] - sorted_scores[i]
        if gap > margin:
            # Sharp drop-off — the cluster ends here
            break
        refined = i + 1

    result = max(min_k, min(max_k, refined if refined > 0 else chosen))

    log.debug(
        "adaptive_k.selected",
        chosen_before_margin=chosen,
        final_k=result,
        top_score=round(sorted_scores[0], 4) if sorted_scores else None,
    )
    return result


# ── 2. Chunk-Mean Memory Compression ─────────────────────────────────────────


def compress_memory_group(memories: list[str], max_tokens: int = 100) -> str:
    """
    Compress a group of related memories into a single injected line.

    Inspired by MSA's chunk-mean pooling of KV caches before routing: rather than
    concatenating every memory verbatim we surface a single representative line,
    capping T_aug growth when multiple memories cover the same topic.

    Algorithm:
      - If only one memory, return it (truncated to max_tokens words if needed).
      - Otherwise pick the shortest summary (most likely the most distilled fact),
        truncate it to max_tokens words, and append "(+N more)" where N is the
        number of suppressed memories.

    Args:
        memories:   List of memory summary strings for a related group.
        max_tokens: Approximate word-based budget for the returned line.
                    (Word count is used as a cheap proxy for token count to avoid
                    a full tokeniser call in the hot path.)

    Returns:
        A single compressed summary string.

    Example:
        >>> compress_memory_group(
        ...     ["User uses Python daily", "User works in Python", "User prefers Python over Java"],
        ...     max_tokens=10,
        ... )
        "User uses Python daily (+2 more)"
    """
    if not memories:
        return ""

    cleaned = [m.strip() for m in memories if m and m.strip()]
    if not cleaned:
        return ""

    if len(cleaned) == 1:
        words = cleaned[0].split()
        if len(words) <= max_tokens:
            return cleaned[0]
        return " ".join(words[:max_tokens]) + "…"

    # Pick the shortest (most distilled) summary as the representative.
    representative = min(cleaned, key=len)
    others_count = len(cleaned) - 1

    words = representative.split()
    if len(words) > max_tokens:
        representative = " ".join(words[:max_tokens]) + "…"

    return f"{representative} (+{others_count} more)"


# ── 3. Multi-hop Memory Retrieval ─────────────────────────────────────────────


async def multi_hop_retrieve(
    db: "AsyncSession",
    user_id: uuid.UUID,
    query: str,
    embedding_service: "EmbeddingService",
    hops: int = 2,
    k_per_hop: int = 3,
) -> list[tuple["Memory", float]]:
    """
    Two-pass (multi-hop) memory retrieval inspired by MSA Memory Interleave.

    MSA interleaves "generative retrieval → context expansion → generation" in
    multiple rounds to surface bridging memories that a single-hop search misses.
    We adapt this for MemLayer's retrieval-augmented architecture:

      Hop 1: Retrieve top-k memories directly relevant to `query`.
      Hop 2: Use the hop-1 summaries/content as secondary queries to find memories
             that are *adjacent* in the knowledge graph (bridging facts).
      Result: Deduplicate by memory id, re-rank the union by composite score.

    Args:
        db:                AsyncSession for DB access.
        user_id:           The requesting user's UUID.
        query:             Natural-language query string.
        embedding_service: Injected EmbeddingService instance.
        hops:              Number of retrieval hops (currently only 2 are meaningful;
                           additional hops fall back to hop-2 behaviour).
        k_per_hop:         How many memories to retrieve per hop.

    Returns:
        List of (Memory, composite_score) tuples, deduplicated and sorted descending
        by score.

    Example:
        query = "what's blocking my project?"
        Hop 1: ["project is blocked by auth migration", "auth uses MD5"]
        Hop 2: queries with hop-1 summaries → ["MD5 ticket assigned to Bob"]
        Result: all three, re-ranked
    """
    # Import inside function to avoid circular imports at module load time.
    from app.services.retrieval_service import (
        RetrievalService,
        W_SIMILARITY,
        W_RECENCY,
        W_IMPORTANCE,
        _recency_score,
    )
    from app.services.encryption_service import decrypt

    _svc = RetrievalService()

    # ── Hop 1 ────────────────────────────────────────────────────────────────
    hop1_embedding = await embedding_service.embed(query)
    hop1_raw = await _svc._vector_search(
        db,
        user_id=user_id,
        query_embedding=hop1_embedding,
        limit=k_per_hop * 3,
    )

    # Decrypt summaries so we can use them as hop-2 queries
    salt = await _svc._get_salt(db, user_id)
    hop1_scored: dict[uuid.UUID, tuple["Memory", float]] = {}
    hop1_queries: list[str] = []

    for memory, cosine_sim in hop1_raw:
        recency = _recency_score(memory.captured_at)
        composite = (
            W_SIMILARITY * cosine_sim
            + W_RECENCY * recency
            + W_IMPORTANCE * memory.importance_score
        )
        try:
            decrypted_summary = decrypt(memory.summary, salt) if memory.summary else None
            decrypted_content = decrypt(memory.content, salt)
        except Exception:
            decrypted_summary = None
            decrypted_content = "[decryption error]"

        memory.summary = decrypted_summary
        memory.content = decrypted_content

        hop1_scored[memory.id] = (memory, composite)

        # Use the summary as a hop-2 query; fall back to a content prefix
        hop_query = decrypted_summary or decrypted_content[:200]
        if hop_query and hop_query != "[decryption error]":
            hop1_queries.append(hop_query)

    if hops < 2 or not hop1_queries:
        results = sorted(hop1_scored.values(), key=lambda x: x[1], reverse=True)
        return results[:k_per_hop]

    # ── Hop 2 ────────────────────────────────────────────────────────────────
    # Embed all hop-1 queries in one batched call for efficiency.
    hop2_embeddings = await embedding_service.embed_batch(hop1_queries[:k_per_hop])

    hop2_scored: dict[uuid.UUID, tuple["Memory", float]] = {}
    for hop2_emb in hop2_embeddings:
        hop2_raw = await _svc._vector_search(
            db,
            user_id=user_id,
            query_embedding=hop2_emb,
            limit=k_per_hop * 2,
        )
        for memory, cosine_sim in hop2_raw:
            if memory.id in hop1_scored:
                continue  # already have this one from hop 1

            recency = _recency_score(memory.captured_at)
            composite = (
                W_SIMILARITY * cosine_sim
                + W_RECENCY * recency
                + W_IMPORTANCE * memory.importance_score
            )

            if memory.id in hop2_scored:
                # Keep the higher score if we've seen this memory before
                _, existing_score = hop2_scored[memory.id]
                if composite <= existing_score:
                    continue

            try:
                memory.summary = decrypt(memory.summary, salt) if memory.summary else None
                memory.content = decrypt(memory.content, salt)
            except Exception:
                memory.summary = None
                memory.content = "[decryption error]"

            hop2_scored[memory.id] = (memory, composite)

    # ── Merge, deduplicate, re-rank ───────────────────────────────────────────
    combined = {**hop1_scored, **hop2_scored}
    results = sorted(combined.values(), key=lambda x: x[1], reverse=True)

    log.debug(
        "multi_hop_retrieve.complete",
        hop1_count=len(hop1_scored),
        hop2_new=len(hop2_scored),
        total_unique=len(combined),
    )

    return results
