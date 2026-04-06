"""
Analytics service — tracks token and cost savings per request.

Each call to `log_request` writes one AnalyticsLog row.
The summary / timeline / breakdown helpers run aggregate SQL queries.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from sqlalchemy import func, select, and_, cast, Date, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AnalyticsLog
from app.schemas.analytics import (
    AnalyticsLogCreate,
    AnalyticsSummary,
    AnalyticsTimeline,
    ProviderBreakdown,
    ROISummary,
)
from app.services.pricing import calculate_cost_savings

log = structlog.get_logger()

# Conservative estimate of full conversation context in tokens.
# Callers can override this when they have a better estimate.
DEFAULT_FULL_CONTEXT_TOKENS = 15_000


class AnalyticsService:

    async def log_request(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        platform: str,
        model: str,
        original_tokens: int,
        augmented_tokens: int,
        hit_count: int,
        latency_ms: int,
        request_id: Optional[uuid.UUID] = None,
        ingestion_cost_usd: float = 0.0,
        ingestion_input_tokens: int = 0,
        ingestion_output_tokens: int = 0,
    ) -> AnalyticsLog:
        """
        Persist one analytics record.

        Computes:
            tokens_saved      = original_tokens - augmented_tokens
            cost_saved_usd    = tokens_saved * price_per_token(platform, model)
            compression_ratio = original_tokens / augmented_tokens  (1.0 if augmented == 0)
        """
        tokens_saved = max(0, original_tokens - augmented_tokens)
        cost_saved_usd = calculate_cost_savings(tokens_saved, platform, model)
        compression_ratio = (
            round(original_tokens / augmented_tokens, 4)
            if augmented_tokens > 0
            else float(original_tokens) if original_tokens > 0 else 1.0
        )

        entry = AnalyticsLog(
            user_id=user_id,
            request_id=request_id or uuid.uuid4(),
            platform=platform.lower(),
            model=model.lower(),
            original_tokens=original_tokens,
            augmented_tokens=augmented_tokens,
            tokens_saved=tokens_saved,
            cost_saved_usd=cost_saved_usd,
            ingestion_cost_usd=ingestion_cost_usd,
            ingestion_input_tokens=ingestion_input_tokens,
            ingestion_output_tokens=ingestion_output_tokens,
            retrieval_hit_count=hit_count,
            retrieval_latency_ms=latency_ms,
            compression_ratio=compression_ratio,
            created_at=datetime.now(timezone.utc),
        )

        db.add(entry)
        await db.commit()
        await db.refresh(entry)

        log.info(
            "analytics.logged",
            user_id=str(user_id),
            platform=platform,
            model=model,
            tokens_saved=tokens_saved,
            cost_saved_usd=cost_saved_usd,
            hit_count=hit_count,
            latency_ms=latency_ms,
        )
        return entry

    async def get_summary(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        days: int = 30,
    ) -> AnalyticsSummary:
        """Return aggregate statistics for the last `days` days."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = select(
            func.coalesce(func.sum(AnalyticsLog.cost_saved_usd), 0.0).label("total_savings_usd"),
            func.coalesce(func.sum(AnalyticsLog.tokens_saved), 0).label("total_tokens_saved"),
            func.count(AnalyticsLog.id).label("total_requests"),
            func.coalesce(func.avg(AnalyticsLog.compression_ratio), 1.0).label("avg_compression_ratio"),
            func.coalesce(func.avg(AnalyticsLog.retrieval_latency_ms), 0.0).label("avg_retrieval_latency_ms"),
            func.coalesce(func.sum(AnalyticsLog.ingestion_cost_usd), 0.0).label("total_ingestion_cost_usd"),
        ).where(
            and_(
                AnalyticsLog.user_id == user_id,
                AnalyticsLog.created_at >= since,
            )
        )

        result = await db.execute(stmt)
        row = result.one()

        total_retrieval_savings = round(float(row.total_savings_usd), 6)
        total_ingestion_cost = round(float(row.total_ingestion_cost_usd), 6)
        net_savings = round(total_retrieval_savings - total_ingestion_cost, 6)
        total_requests = int(row.total_requests)

        # break-even: how many retrievals needed to cover the average ingestion cost?
        # Uses per-request averages: avg_ingestion_cost / avg_retrieval_savings_per_request.
        if total_requests > 0 and total_retrieval_savings > 0:
            avg_retrieval_savings = total_retrieval_savings / total_requests
            avg_ingestion_cost = total_ingestion_cost / total_requests
            break_even = round(avg_ingestion_cost / avg_retrieval_savings, 4) if avg_retrieval_savings > 0 else 0.0
        else:
            break_even = 0.0

        return AnalyticsSummary(
            total_savings_usd=total_retrieval_savings,
            total_tokens_saved=int(row.total_tokens_saved),
            total_requests=total_requests,
            avg_compression_ratio=round(float(row.avg_compression_ratio), 4),
            avg_retrieval_latency_ms=round(float(row.avg_retrieval_latency_ms), 2),
            days=days,
            total_retrieval_savings_usd=total_retrieval_savings,
            total_ingestion_cost_usd=total_ingestion_cost,
            net_savings_usd=net_savings,
            break_even_retrievals=break_even,
        )

    async def get_roi(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        days: int = 30,
        ingestion_model: str = "gpt-4o-mini",
    ) -> ROISummary:
        """
        Return a dedicated ROI breakdown for the last `days` days.

        Separates gross retrieval savings from ingestion costs so callers can
        display the full cost equation:
            net_savings = retrieval_savings - ingestion_cost
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = select(
            func.coalesce(func.sum(AnalyticsLog.cost_saved_usd), 0.0).label("total_retrieval_savings"),
            func.coalesce(func.sum(AnalyticsLog.ingestion_cost_usd), 0.0).label("total_ingestion_cost"),
            func.count(AnalyticsLog.id).label("total_requests"),
        ).where(
            and_(
                AnalyticsLog.user_id == user_id,
                AnalyticsLog.created_at >= since,
            )
        )

        result = await db.execute(stmt)
        row = result.one()

        total_retrieval_savings = round(float(row.total_retrieval_savings), 6)
        total_ingestion_cost = round(float(row.total_ingestion_cost), 6)
        net_savings = round(total_retrieval_savings - total_ingestion_cost, 6)
        total_requests = int(row.total_requests)

        if total_requests > 0 and total_retrieval_savings > 0:
            avg_retrieval_savings = total_retrieval_savings / total_requests
            avg_ingestion_cost = total_ingestion_cost / total_requests
            break_even = round(avg_ingestion_cost / avg_retrieval_savings, 4) if avg_retrieval_savings > 0 else 0.0
        else:
            break_even = 0.0

        return ROISummary(
            total_retrieval_savings_usd=total_retrieval_savings,
            total_ingestion_cost_usd=total_ingestion_cost,
            net_savings_usd=net_savings,
            break_even_retrievals=break_even,
            ingestion_model=ingestion_model,
            days=days,
        )

    async def get_timeline(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        days: int = 30,
    ) -> list[AnalyticsTimeline]:
        """Return daily aggregates for the last `days` days, ordered ascending."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = (
            select(
                cast(AnalyticsLog.created_at, Date).label("day"),
                func.sum(AnalyticsLog.tokens_saved).label("tokens_saved"),
                func.sum(AnalyticsLog.cost_saved_usd).label("cost_saved_usd"),
                func.count(AnalyticsLog.id).label("requests"),
            )
            .where(
                and_(
                    AnalyticsLog.user_id == user_id,
                    AnalyticsLog.created_at >= since,
                )
            )
            .group_by(cast(AnalyticsLog.created_at, Date))
            .order_by(cast(AnalyticsLog.created_at, Date))
        )

        result = await db.execute(stmt)
        rows = result.all()

        return [
            AnalyticsTimeline(
                date=row.day,
                tokens_saved=int(row.tokens_saved),
                cost_saved_usd=round(float(row.cost_saved_usd), 6),
                requests=int(row.requests),
            )
            for row in rows
        ]

    async def get_provider_breakdown(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[ProviderBreakdown]:
        """Return per-platform aggregates for all time, ordered by total savings descending."""

        # Main aggregation per platform
        agg_stmt = (
            select(
                AnalyticsLog.platform,
                func.count(AnalyticsLog.id).label("total_requests"),
                func.coalesce(func.sum(AnalyticsLog.tokens_saved), 0).label("total_tokens_saved"),
                func.coalesce(func.sum(AnalyticsLog.cost_saved_usd), 0.0).label("total_savings_usd"),
                func.coalesce(func.avg(AnalyticsLog.compression_ratio), 1.0).label("avg_compression_ratio"),
                func.coalesce(func.avg(AnalyticsLog.retrieval_latency_ms), 0.0).label("avg_retrieval_latency_ms"),
            )
            .where(AnalyticsLog.user_id == user_id)
            .group_by(AnalyticsLog.platform)
            .order_by(func.sum(AnalyticsLog.cost_saved_usd).desc())
        )

        agg_result = await db.execute(agg_stmt)
        agg_rows = agg_result.all()

        # For each platform, find the most-used model (a separate query per platform
        # is simpler and avoids complex window-function cross-database compatibility).
        breakdowns: list[ProviderBreakdown] = []
        for row in agg_rows:
            most_used_model = await self._most_used_model(db, user_id, row.platform)
            breakdowns.append(
                ProviderBreakdown(
                    platform=row.platform,
                    total_requests=int(row.total_requests),
                    total_tokens_saved=int(row.total_tokens_saved),
                    total_savings_usd=round(float(row.total_savings_usd), 6),
                    avg_compression_ratio=round(float(row.avg_compression_ratio), 4),
                    avg_retrieval_latency_ms=round(float(row.avg_retrieval_latency_ms), 2),
                    most_used_model=most_used_model,
                )
            )

        return breakdowns

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _most_used_model(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        platform: str,
    ) -> Optional[str]:
        stmt = (
            select(AnalyticsLog.model)
            .where(
                and_(
                    AnalyticsLog.user_id == user_id,
                    AnalyticsLog.platform == platform,
                )
            )
            .group_by(AnalyticsLog.model)
            .order_by(func.count(AnalyticsLog.id).desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.first()
        return row[0] if row else None


analytics_service = AnalyticsService()
