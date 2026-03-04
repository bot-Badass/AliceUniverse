from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GrowthRecord


class GrowthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_record(
        self,
        record_type: str,
        created_by: int,
        value: float | None = None,
        title: str | None = None,
        note: str | None = None,
        recorded_on: date | None = None,
    ) -> GrowthRecord:
        record = GrowthRecord(
            record_type=record_type,
            value=value,
            title=title,
            note=note,
            created_by=created_by,
            recorded_on=recorded_on or date.today(),
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def latest_record(self, record_type: str) -> GrowthRecord | None:
        result = await self.session.execute(
            select(GrowthRecord)
            .where(GrowthRecord.record_type == record_type)
            .order_by(GrowthRecord.recorded_on.desc(), GrowthRecord.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def previous_record_before(self, record_type: str, record_id: int) -> GrowthRecord | None:
        result = await self.session.execute(
            select(GrowthRecord)
            .where(GrowthRecord.record_type == record_type)
            .where(GrowthRecord.id != record_id)
            .order_by(GrowthRecord.recorded_on.desc(), GrowthRecord.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def needs_weight_reminder(self) -> bool:
        latest = await self.latest_record("weight")
        if latest is None:
            return True
        return (date.today() - latest.recorded_on).days >= 7

    async def needs_height_reminder(self) -> bool:
        latest = await self.latest_record("height")
        if latest is None:
            return True
        return (date.today() - latest.recorded_on).days >= 30
