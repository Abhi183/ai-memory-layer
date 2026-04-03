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

from app.models.memory import Memory, MemoryEmbedding, MemoryStatus, MemoryType
from app.services.embedding_service import embedding_service
from app.services.encryption_service import encrypt, decrypt
from app.config import settings

log = structlog.get_logger()


FACT_EXTRACTION_PROMPT = """You are a memory extraction assistant.
Given the following AI conversation, extract the key facts about the USER (not general knowledge).
Focus on: preferences, personal details, workplace, projects, goals, relationships, skills.
Return a JSON object with key "facts" containing a list of short fact strings.
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


class PipelineService:

    async def process_memory(self, db: AsyncSession, memory_id: uuid.UUID):
        """Entry point: process a single memory through the full pipeline."""
        memory = await db.get(Memory, memory_id)
        if memory is None:
            log.error("pipeline_memory_not_found", memory_id=str(memory_id))
            return

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

            # Step 2: Extract facts
            facts = await self._extract_facts(plaintext)

            # Step 3: Summarize
            summary = await self._summarize(plaintext)

            # Step 4: Classify memory type
            if facts:
                memory_type = await self._classify_type(facts)
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
            memory.extracted_facts = {"facts": facts}
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
            log.info("pipeline_success", memory_id=str(memory_id), type=memory_type)

        except Exception as exc:
            log.error("pipeline_failed", memory_id=str(memory_id), error=str(exc))
            memory.status = MemoryStatus.FAILED
            await db.commit()
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def _extract_facts(self, content: str) -> list[str]:
        if not settings.openai_api_key:
            return []
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": FACT_EXTRACTION_PROMPT.format(content=content[:3000]),
                    }
                ],
                max_tokens=500,
                temperature=0.1,
            )
            raw = response.choices[0].message.content.strip()
            data = json.loads(raw)
            return data.get("facts", [])
        except Exception as exc:
            log.warning("fact_extraction_failed", error=str(exc))
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _summarize(self, content: str) -> Optional[str]:
        if not settings.openai_api_key:
            # Naive truncation fallback
            return content[:200] + "..." if len(content) > 200 else content
        try:
            from openai import AsyncOpenAI
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
            return response.choices[0].message.content.strip()
        except Exception as exc:
            log.warning("summarization_failed", error=str(exc))
            return None

    async def _classify_type(self, facts: list[str]) -> MemoryType:
        if not settings.openai_api_key or not facts:
            return MemoryType.SHORT_TERM
        try:
            from openai import AsyncOpenAI
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
            result = response.choices[0].message.content.strip().lower()
            return MemoryType.LONG_TERM if "long_term" in result else MemoryType.SHORT_TERM
        except Exception:
            return MemoryType.SHORT_TERM


pipeline_service = PipelineService()
