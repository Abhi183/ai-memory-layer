"""
Celery worker for async memory processing.

Tasks run in separate worker processes so the API stays responsive.
Redis acts as both the broker and result backend.

Start the worker with:
    celery -A app.workers.memory_worker worker --loglevel=info --concurrency=4
"""

import asyncio
from celery import Celery
from celery.utils.log import get_task_logger
from app.config import settings

logger = get_task_logger(__name__)

celery_app = Celery(
    "memory_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,          # Only ack after successful processing
    worker_prefetch_multiplier=1, # One task at a time per worker (memory-heavy tasks)
    task_max_retries=3,
    task_default_retry_delay=30,  # seconds
)


@celery_app.task(
    bind=True,
    name="process_memory",
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
)
def process_memory_task(self, memory_id: str, user_id: str):
    """
    Celery task: run the full memory processing pipeline for a given memory.
    Bridges sync Celery with our async pipeline service.
    """
    logger.info(f"Processing memory {memory_id} for user {user_id}")
    try:
        asyncio.run(_async_process(memory_id, user_id))
        logger.info(f"Memory {memory_id} processed successfully")
    except Exception as exc:
        logger.error(f"Failed to process memory {memory_id}: {exc}")
        raise


async def _async_process(memory_id: str, user_id: str):
    import uuid
    from app.database import AsyncSessionLocal
    from app.services.pipeline_service import pipeline_service

    async with AsyncSessionLocal() as db:
        await pipeline_service.process_memory(db, uuid.UUID(memory_id))


def enqueue_memory_processing(memory_id: str, user_id: str):
    """
    Enqueue a memory processing task.
    Falls back to synchronous processing if Celery is unavailable (dev mode).
    """
    try:
        process_memory_task.delay(memory_id, user_id)
    except Exception:
        # Celery not available — run synchronously (useful for local dev without Redis)
        logger.warning("Celery unavailable, processing synchronously")
        asyncio.create_task(_async_process(memory_id, user_id))
