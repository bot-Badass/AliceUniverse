from datetime import datetime
from typing import List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.crm.models import Reminder
from app.db import engine


async def create_reminder(
    lead_id: int,
    manager_id: int,
    remind_at: datetime,
    reminder_type: str,
    message: str,
) -> Reminder:
    async with AsyncSession(engine) as session:
        reminder = Reminder(
            lead_id=lead_id,
            manager_id=manager_id,
            remind_at=remind_at,
            reminder_type=reminder_type,
            message=message,
        )
        session.add(reminder)
        await session.commit()
        await session.refresh(reminder)
        return reminder


async def get_due_reminders(now_utc: datetime) -> List[Reminder]:
    async with AsyncSession(engine) as session:
        stmt = (
            select(Reminder)
            .where(and_(Reminder.remind_at <= now_utc, Reminder.is_completed.is_(False)))
            .order_by(Reminder.remind_at)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def mark_reminder_completed(reminder_id: int) -> None:
    async with AsyncSession(engine) as session:
        reminder = await session.get(Reminder, reminder_id)
        if reminder:
            reminder.is_completed = True
            reminder.completed_at = datetime.utcnow()
            await session.commit()