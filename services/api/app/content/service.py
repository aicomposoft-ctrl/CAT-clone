"""Business logic for the content scores domain."""

from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.content import repository
from app.content.schemas import (
    ContentScoreDrilldown,
    ContentScoreHistory,
    ContentScoreItem,
    ContentScorePage,
)


async def get_content_scores(
    db: AsyncSession,
    org_id: UUID,
    *,
    platform_id: Optional[UUID] = None,
    brand_id: Optional[UUID] = None,
    score_max: Optional[float] = None,
    score_min: Optional[float] = None,
    scored_at: Optional[date] = None,
    page: int = 1,
    size: int = 50,
) -> ContentScorePage:
    rows, total = await repository.fetch_scores_page(
        db,
        org_id,
        platform_id=platform_id,
        brand_id=brand_id,
        score_max=score_max,
        score_min=score_min,
        scored_at=scored_at,
        page=page,
        size=size,
    )

    items = [
        ContentScoreItem(
            id=row.id,
            sku_platform_id=row.sku_platform_id,
            sku_id=row.sku_id,
            sku_name=row.sku_name,
            article=row.article,
            brand_id=row.brand_id,
            brand_name=row.brand_name,
            platform_id=row.platform_id,
            platform_name=row.platform_name,
            platform_url=row.platform_url,
            scored_at=row.scored_at,
            content_total=row.content_total,
            image_score=row.image_score,
            description_score=row.description_score,
            composition_score=row.composition_score,
            collected_image_url=row.collected_image_url,
            created_at=row.created_at,
        )
        for row in rows
    ]

    return ContentScorePage(items=items, total=total, page=page, size=size)


async def get_content_drilldown(
    db: AsyncSession,
    org_id: UUID,
    sku_platform_id: UUID,
) -> Optional[ContentScoreDrilldown]:
    import asyncio

    row, history_rows = await asyncio.gather(
        repository.fetch_drilldown(db, org_id, sku_platform_id),
        repository.fetch_history(db, org_id, sku_platform_id, days=30),
    )
    if row is None:
        return None
    history = [
        ContentScoreHistory(scored_at=h.scored_at, content_total=h.content_total)
        for h in history_rows
    ]

    return ContentScoreDrilldown(
        id=row.id,
        sku_platform_id=row.sku_platform_id,
        sku_id=row.sku_id,
        sku_name=row.sku_name,
        article=row.article,
        brand_id=row.brand_id,
        brand_name=row.brand_name,
        platform_id=row.platform_id,
        platform_name=row.platform_name,
        platform_url=row.platform_url,
        scored_at=row.scored_at,
        content_total=row.content_total,
        image_score=row.image_score,
        description_score=row.description_score,
        composition_score=row.composition_score,
        collected_image_url=row.collected_image_url,
        collected_description=row.collected_description,
        collected_composition=row.collected_composition,
        collected_title=row.collected_title,
        created_at=row.created_at,
        reference_image_url=row.reference_image_url,
        reference_description=row.reference_description,
        reference_composition=row.reference_composition,
        history=history,
    )
