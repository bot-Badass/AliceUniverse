from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.crm.models import Reminder, Lead


async def create_reminder(
    lead_id: int,
    manager_id: int,
    remind_at: datetime,
    reminder_type: str,
    message: str,
) -> Reminder:
    async with SessionLocal() as session:
        reminder = Reminder(
            lead_id=lead_id,
            manager_id=manager_id,
            remind_at=remind_at,
            reminder_type=reminder_type,
            message=message,
            is_completed=False,
        )
        session.add(reminder)
        await session.commit()
        await session.refresh(reminder)
        return reminder


async def get_due_reminders(now_utc: datetime) -> list[Reminder]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Reminder)
            .where(Reminder.is_completed.is_(False))
            .where(Reminder.remind_at <= now_utc)
            .order_by(Reminder.remind_at.asc())
        )
        return list(result.scalars().all())


async def mark_reminder_completed(reminder_id: int) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(Reminder)
            .where(Reminder.id == reminder_id)
            .values(is_completed=True, completed_at=datetime.utcnow())
        )
        await session.commit()


async def update_reminder_time(reminder_id: int, new_time: datetime) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(Reminder)
            .where(Reminder.id == reminder_id)
            .values(remind_at=new_time, is_completed=False)
        )
        await session.commit()


async def get_reminder(reminder_id: int) -> Reminder | None:
    async with SessionLocal() as session:
        return await session.get(Reminder, reminder_id)


async def get_lead(lead_id: int) -> Lead | None:
    async with SessionLocal() as session:
        return await session.get(Lead, lead_id)


async def list_upcoming_reminders(manager_id: int, limit: int = 10) -> list[Reminder]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Reminder)
            .where(Reminder.manager_id == manager_id)
            .where(Reminder.is_completed.is_(False))
            .order_by(Reminder.remind_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
