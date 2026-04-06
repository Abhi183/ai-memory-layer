import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.analytics import AnalyticsLog
from app.schemas.analytics import (
    AnalyticsLogRead,
    AnalyticsSummary,
    AnalyticsTimeline,
    ProviderBreakdown,
    ROISummary,
)
from app.services.analytics_service import analytics_service
from sqlalchemy import select, and_
import structlog

log = structlog.get_logger()

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def get_summary(
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return aggregate token and cost savings for the authenticated user
    over the last `days` days.
    """
    return await analytics_service.get_summary(db, user.id, days=days)


@router.get("/timeline", response_model=list[AnalyticsTimeline])
async def get_timeline(
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return daily time-series data (tokens saved, cost saved, request count)
    for the last `days` days, ordered oldest-first.
    """
    return await analytics_service.get_timeline(db, user.id, days=days)


@router.get("/providers", response_model=list[ProviderBreakdown])
async def get_provider_breakdown(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return per-provider (platform) aggregated statistics for all time,
    ordered by total savings descending.
    """
    return await analytics_service.get_provider_breakdown(db, user.id)


@router.get("/roi", response_model=ROISummary)
async def get_roi(
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
    ingestion_model: str = Query(
        default="gpt-4o-mini",
        description="Model used for ingestion pipeline cost calculations",
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a full ROI breakdown separating gross retrieval savings from ingestion costs.

    Example response:
    ```json
    {
      "total_retrieval_savings_usd": 12.45,
      "total_ingestion_cost_usd": 1.23,
      "net_savings_usd": 11.22,
      "break_even_retrievals": 3.2,
      "ingestion_model": "gpt-4o-mini",
      "days": 30
    }
    ```

    `break_even_retrievals` is the average number of times a memory must be retrieved
    to cover its ingestion cost. Values below 1.0 mean ingestion pays for itself on
    the very first retrieval.
    """
    return await analytics_service.get_roi(db, user.id, days=days, ingestion_model=ingestion_model)


@router.get("/logs", response_model=list[AnalyticsLogRead])
async def list_logs(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of records to return"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
    platform: str | None = Query(default=None, description="Filter by platform"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a paginated list of raw analytics log entries for the authenticated user,
    ordered most-recent first.
    """
    conditions = [AnalyticsLog.user_id == user.id]
    if platform:
        conditions.append(AnalyticsLog.platform == platform.lower())

    stmt = (
        select(AnalyticsLog)
        .where(and_(*conditions))
        .order_by(AnalyticsLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    logs = result.scalars().all()

    log.debug(
        "analytics.logs.listed",
        user_id=str(user.id),
        count=len(logs),
        offset=offset,
        platform=platform,
    )
    return logs
