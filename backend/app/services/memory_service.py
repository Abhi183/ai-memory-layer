"""
Memory CRUD service — handles create, read, update, delete with encryption.
All content is encrypted before write and decrypted after read.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_
from sqlalchemy.orm import selectinload

from app.models.memory import Memory, Tag, Source, MemoryType, MemoryStatus
from app.models.user import User
from app.schemas.memory import MemoryCreate, MemoryUpdate, MemoryCaptureRequest
from app.services.encryption_service import encrypt, decrypt
from app.workers.memory_worker import enqueue_memory_processing

log = structlog.get_logger()

# Short-term memories expire after this many days if not accessed
SHORT_TERM_TTL_DAYS = 7


class MemoryService:

    async def capture(
        self,
        db: AsyncSession,
        user: User,
        capture: MemoryCaptureRequest,
    ) -> Memory:
        """
        Entry point from browser extension / CLI.
        Combines prompt + response into a single content blob and enqueues
        the processing pipeline asynchronously.
        """
        combined = f"USER: {capture.prompt}\n\nASSISTANT: {capture.response}"
        encrypted_content = encrypt(combined, user.encryption_salt)

        # Upsert source
        source = await self._get_or_create_source(
            db, user.id, capture.platform, capture.source_url, capture.session_id
        )

        memory = Memory(
            user_id=user.id,
            source_id=source.id,
            content=encrypted_content,
            source_platform=capture.platform,
            memory_type=MemoryType.SHORT_TERM,
            status=MemoryStatus.PENDING,
        )
        db.add(memory)
        await db.flush()  # get the ID without committing

        # Apply tags
        if capture.tags:
            tags = await self._get_or_create_tags(db, capture.tags)
            memory.tags.extend(tags)

        await db.commit()
        await db.refresh(memory)

        # Kick off async pipeline (extract facts → summarize → embed)
        try:
            enqueue_memory_processing(str(memory.id), str(user.id))
        except Exception as exc:
            log.warning("pipeline_enqueue_failed", memory_id=str(memory.id), error=str(exc))
            # Non-fatal: the memory is saved, just not yet processed

        return memory

    async def create(
        self,
        db: AsyncSession,
        user: User,
        data: MemoryCreate,
    ) -> Memory:
        """Direct memory creation (used by API clients, not the capture flow)."""
        encrypted = encrypt(data.content, user.encryption_salt)
        memory = Memory(
            user_id=user.id,
            content=encrypted,
            memory_type=data.memory_type,
            source_platform=data.source_platform,
            status=MemoryStatus.PENDING,
        )
        if data.memory_type == MemoryType.SHORT_TERM:
            memory.expires_at = datetime.utcnow() + timedelta(days=SHORT_TERM_TTL_DAYS)

        db.add(memory)
        await db.flush()

        if data.tags:
            tags = await self._get_or_create_tags(db, data.tags)
            memory.tags.extend(tags)

        await db.commit()
        await db.refresh(memory, ["tags"])
        enqueue_memory_processing(str(memory.id), str(user.id))
        return self._decrypt_memory(memory, user.encryption_salt)

    async def get(
        self,
        db: AsyncSession,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[Memory]:
        result = await db.execute(
            select(Memory)
            .options(selectinload(Memory.tags), selectinload(Memory.source))
            .where(and_(Memory.id == memory_id, Memory.user_id == user_id))
        )
        memory = result.scalar_one_or_none()
        if memory is None:
            return None
        # Bump access count
        await db.execute(
            update(Memory)
            .where(Memory.id == memory_id)
            .values(access_count=Memory.access_count + 1)
        )
        return self._decrypt_memory(memory, await self._get_salt(db, user_id))

    async def list_memories(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        memory_type: Optional[MemoryType] = None,
        platform: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        q = (
            select(Memory)
            .options(selectinload(Memory.tags))
            .where(
                and_(
                    Memory.user_id == user_id,
                    Memory.status != MemoryStatus.ARCHIVED,
                )
            )
            .order_by(Memory.captured_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if memory_type:
            q = q.where(Memory.memory_type == memory_type)
        if platform:
            q = q.where(Memory.source_platform == platform)

        result = await db.execute(q)
        memories = result.scalars().all()
        salt = await self._get_salt(db, user_id)
        return [self._decrypt_memory(m, salt) for m in memories]

    async def update(
        self,
        db: AsyncSession,
        memory_id: uuid.UUID,
        user: User,
        data: MemoryUpdate,
    ) -> Optional[Memory]:
        memory = await db.get(Memory, memory_id)
        if memory is None or memory.user_id != user.id:
            return None

        if data.content is not None:
            memory.content = encrypt(data.content, user.encryption_salt)
            # Re-process to update embeddings
            memory.status = MemoryStatus.PENDING
            enqueue_memory_processing(str(memory.id), str(user.id))

        if data.summary is not None:
            memory.summary = encrypt(data.summary, user.encryption_salt)
        if data.memory_type is not None:
            memory.memory_type = data.memory_type
        if data.importance_score is not None:
            memory.importance_score = data.importance_score
        if data.tags is not None:
            tags = await self._get_or_create_tags(db, data.tags)
            memory.tags = tags

        await db.commit()
        await db.refresh(memory, ["tags"])
        return self._decrypt_memory(memory, user.encryption_salt)

    async def delete(
        self,
        db: AsyncSession,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        result = await db.execute(
            delete(Memory).where(
                and_(Memory.id == memory_id, Memory.user_id == user_id)
            )
        )
        await db.commit()
        return result.rowcount > 0

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _decrypt_memory(self, memory: Memory, salt: str) -> Memory:
        """Decrypt content/summary in-place and return the object."""
        try:
            memory.content = decrypt(memory.content, salt)
        except Exception:
            memory.content = "[decryption failed]"
        if memory.summary:
            try:
                memory.summary = decrypt(memory.summary, salt)
            except Exception:
                memory.summary = None
        return memory

    async def _get_salt(self, db: AsyncSession, user_id: uuid.UUID) -> str:
        result = await db.execute(
            select(User.encryption_salt).where(User.id == user_id)
        )
        return result.scalar_one()

    async def _get_or_create_tags(self, db: AsyncSession, names: list[str]) -> list[Tag]:
        tags = []
        for name in names:
            name = name.lower().strip()
            result = await db.execute(select(Tag).where(Tag.name == name))
            tag = result.scalar_one_or_none()
            if tag is None:
                tag = Tag(name=name)
                db.add(tag)
                await db.flush()
            tags.append(tag)
        return tags

    async def _get_or_create_source(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        platform: str,
        source_url: Optional[str],
        session_id: Optional[str],
    ) -> Source:
        if session_id:
            result = await db.execute(
                select(Source).where(
                    and_(
                        Source.user_id == user_id,
                        Source.session_id == session_id,
                    )
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        source = Source(
            user_id=user_id,
            platform=platform,
            source_url=source_url,
            session_id=session_id,
        )
        db.add(source)
        await db.flush()
        return source


memory_service = MemoryService()
