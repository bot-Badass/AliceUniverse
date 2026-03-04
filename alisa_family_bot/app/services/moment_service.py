from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MemorableMoment


class MemorableMomentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_moment(
        self,
        title: str,
        description: str | None,
        moment_date: date,
        created_by: int,
        hashtags: str | None = None,
        media_type: str | None = None,
        media_file_id: str | None = None,
    ) -> MemorableMoment:
        moment = MemorableMoment(
            title=title,
            description=description,
            date=moment_date,
            created_by=created_by,
            hashtags=hashtags,
            media_type=media_type,
            media_file_id=media_file_id,
        )
        self.session.add(moment)
        await self.session.commit()
        await self.session.refresh(moment)
        return moment

    async def get_by_id(self, moment_id: int) -> MemorableMoment | None:
        result = await self.session.execute(select(MemorableMoment).where(MemorableMoment.id == moment_id))
        return result.scalar_one_or_none()
