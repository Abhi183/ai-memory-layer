"""
Memory processing pipeline.

Steps:
  1. Load raw memory from DB (still encrypted).
  2. Decrypt content.
  3. Extract key facts using LLM.
  4. Generate summary using LLM.
  5. Create embeddings (chunked if needed).
  6. Classify memory type (short/long-term) based on content.
  7. Store embeddings and update memory status → ACTIVE.

All LLM calls use tenacity retry with exponential back-off.
"""

import uuid
import json
from datetime import datetime, timezone
from typing import Optional
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from app.models.memory import Memory, MemoryEmbedding, MemoryStatus, MemoryType
from app.services.embedding_service import embedding_service
from app.services.encryption_service import encrypt, decrypt
from app.services.pricing import calculate_ingestion_cost
from app.config import settings

log = structlog.get_logger()


FACT_EXTRACTION_PROMPT = """You are a memory extraction assistant.
Given the following AI conversation, extract the key facts about the USER (not general knowledge).
Focus on: preferences, personal details, workplace, projects, goals, relationships, skills.

Also identify if any facts in this conversation CONTRADICT or SUPERSEDE something that was
previously true. For example: a user switching frameworks, completing a project, or changing
a preference.

Return a JSON object with exactly two keys:
  "facts": list of short strings describing NEW facts about the user
  "invalidates_previous_fact": list of short strings describing OLD facts that are now stale
    (e.g. "User was using React" when user has switched to Vue). Leave empty if nothing is invalidated.

Return ONLY valid JSON, no other text.

Conversation:
{content}
"""

SUMMARIZATION_PROMPT = """Summarize the following AI conversation in 1-2 sentences.
Focus on what the user wanted and what was resolved. Be concise.
Return only the summary text, no preamble.

Conversation:
{content}
"""

TYPE_CLASSIFICATION_PROMPT = """Given these extracted facts, decide if this memory should be:
- "long_term": Contains persistent personal information (name, job, skills, preferences, goals)
- "short_term": A transient interaction with no lasting personal facts

Facts: {facts}

Return ONLY "long_term" or "short_term".
"""


class IngestionTokenUsage:
    """Accumulates token counts across all pipeline LLM calls."""

    def __init__(self) -> None:
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def cost_usd(self, model: str = "gpt-4o-mini") -> float:
        return calculate_ingestion_cost(self.input_tokens, self.output_tokens, model)


class PipelineService:

    async def process_memory(self, db: AsyncSession, memory_id: uuid.UUID) -> IngestionTokenUsage:
        """
        Entry point: process a single memory through the full pipeline.

        Returns an IngestionTokenUsage object so callers can record the
        total LLM cost incurred during ingestion.
        """
        usage = IngestionTokenUsage()

        memory = await db.get(Memory, memory_id)
        if memory is None:
            log.error("pipeline_memory_not_found", memory_id=str(memory_id))
            return usage

        from sqlalchemy import select
        from app.models.user import User
        result = await db.execute(
            select(User.encryption_salt).where(User.id == memory.user_id)
        )
        salt = result.scalar_one()

        try:
            memory.status = MemoryStatus.PROCESSING
            await db.commit()

            # Step 1: Decrypt
            plaintext = decrypt(memory.content, salt)

            # Step 2: Extract facts + invalidation hints
            facts, invalidates, fact_usage = await self._extract_facts(plaintext)
            usage.add(fact_usage.input_tokens, fact_usage.output_tokens)

            # Invalidate stale facts from prior memories when the LLM detected a contradiction
            if invalidates:
                await self._invalidate_stale_facts(db, memory.user_id, invalidates)

            # Step 3: Summarize
            summary, sum_usage = await self._summarize(plaintext)
            usage.add(sum_usage.input_tokens, sum_usage.output_tokens)

            # Step 4: Classify memory type
            if facts:
                memory_type, cls_usage = await self._classify_type(facts)
                usage.add(cls_usage.input_tokens, cls_usage.output_tokens)
            else:
                memory_type = MemoryType.SHORT_TERM

            # Step 5: Embed (use summary for embedding if available, else full content)
            embed_text = summary or plaintext
            chunks = embedding_service.chunk_text(embed_text)

            # Use first chunk's embedding as the primary (simplification for MVP)
            # Production: store all chunk embeddings
            primary_chunk = chunks[0]
            vector = await embedding_service.embed(primary_chunk)

            # Step 6: Persist results
            memory.extracted_facts = {
                "facts": facts,
                "invalidates_previous_fact": invalidates,
            }
            memory.summary = encrypt(summary, salt) if summary else None
            memory.memory_type = memory_type
            memory.token_count = embedding_service.count_tokens(plaintext)
            memory.status = MemoryStatus.ACTIVE
            memory.processed_at = datetime.now(timezone.utc)

            # Upsert embedding
            existing_emb = await db.get(MemoryEmbedding, memory.id)
            if existing_emb:
                existing_emb.embedding = vector
                existing_emb.model_name = settings.openai_embedding_model
            else:
                emb = MemoryEmbedding(
                    memory_id=memory.id,
                    user_id=memory.user_id,
                    embedding=vector,
                    model_name=settings.openai_embedding_model,
                )
                db.add(emb)

            await db.commit()
            log.info(
                "pipeline_success",
                memory_id=str(memory_id),
                type=memory_type,
                ingestion_input_tokens=usage.input_tokens,
                ingestion_output_tokens=usage.output_tokens,
                ingestion_cost_usd=usage.cost_usd(),
            )

        except Exception as exc:
            log.error("pipeline_failed", memory_id=str(memory_id), error=str(exc))
            memory.status = MemoryStatus.FAILED
            await db.commit()
            raise

        return usage

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def _extract_facts(
        self, content: str
    ) -> tuple[list[str], list[str], IngestionTokenUsage]:
        """Returns (facts, invalidates_previous_fact, usage)."""
        usage = IngestionTokenUsage()
        if not settings.openai_api_key:
            return [], [], usage
        try:
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": FACT_EXTRACTION_PROMPT.format(content=content[:3000]),
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=600,
                temperature=0.1,
            )
            if response.usage:
                usage.add(response.usage.prompt_tokens, response.usage.completion_tokens)
            raw = response.choices[0].message.content.strip()
            data = json.loads(raw)
            facts = data.get("facts", [])
            invalidates = data.get("invalidates_previous_fact", [])
            return facts, invalidates, usage
        except Exception as exc:
            log.warning("fact_extraction_failed", error=str(exc))
            return [], [], usage

    async def _invalidate_stale_facts(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        stale_descriptions: list[str],
    ) -> int:
        """
        Find memories whose extracted_facts contain any of the stale descriptions
        (semantic search via simple substring match on fact text) and mark them
        status=INACTIVE so they are excluded from future retrievals.

        Returns the count of memories invalidated.
        """
        from sqlalchemy import select, cast
        from sqlalchemy.dialects.postgresql import JSONB

        invalidated = 0
        for desc in stale_descriptions:
            # Search active memories whose fact text overlaps with the stale description
            result = await db.execute(
                select(Memory).where(
                    Memory.user_id == user_id,
                    Memory.status == MemoryStatus.ACTIVE,
                    # JSONB containment: check if any fact string is a substring of desc
                    # Using a simple ilike on the JSONB text representation
                    Memory.extracted_facts.cast(
                        db.bind.dialect.colspecs.get(type(Memory.extracted_facts), JSONB)
                    ).astext.ilike(f"%{desc[:80]}%"),  # type: ignore[attr-defined]
                )
            )
            stale_memories = result.scalars().all()

            for mem in stale_memories:
                mem.status = MemoryStatus.INACTIVE
                invalidated += 1
                log.info(
                    "memory_invalidated",
                    memory_id=str(mem.id),
                    stale_desc=desc[:80],
                )

        if invalidated:
            await db.commit()
            log.info("stale_facts_invalidated", count=invalidated)

        return invalidated

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _summarize(self, content: str) -> tuple[Optional[str], IngestionTokenUsage]:
        usage = IngestionTokenUsage()
        if not settings.openai_api_key:
            # Naive truncation fallback — no LLM cost
            summary = content[:200] + "..." if len(content) > 200 else content
            return summary, usage
        try:
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": SUMMARIZATION_PROMPT.format(content=content[:3000]),
                    }
                ],
                max_tokens=200,
                temperature=0.3,
            )
            if response.usage:
                usage.add(response.usage.prompt_tokens, response.usage.completion_tokens)
            return response.choices[0].message.content.strip(), usage
        except Exception as exc:
            log.warning("summarization_failed", error=str(exc))
            return None, usage

    async def _classify_type(self, facts: list[str]) -> tuple[MemoryType, IngestionTokenUsage]:
        usage = IngestionTokenUsage()
        if not settings.openai_api_key or not facts:
            return MemoryType.SHORT_TERM, usage
        try:
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": TYPE_CLASSIFICATION_PROMPT.format(
                            facts=", ".join(facts[:10])
                        ),
                    }
                ],
                max_tokens=10,
                temperature=0,
            )
            if response.usage:
                usage.add(response.usage.prompt_tokens, response.usage.completion_tokens)
            result = response.choices[0].message.content.strip().lower()
            memory_type = MemoryType.LONG_TERM if "long_term" in result else MemoryType.SHORT_TERM
            return memory_type, usage
        except Exception:
            return MemoryType.SHORT_TERM, usage


pipeline_service = PipelineService()
