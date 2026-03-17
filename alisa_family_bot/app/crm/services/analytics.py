from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import engine
from app.crm.models import CallLog


async def stats_for_period(manager_id: int, days: int) -> dict[str, int]:
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(CallLog.result, func.count(CallLog.id))
            .where(CallLog.manager_id == manager_id)
            .where(CallLog.created_at >= start)
            .group_by(CallLog.result)
        )
        counts = {row[0]: row[1] for row in result.all()}

    total_calls = sum(counts.values())
    no_answer = counts.get("no_answer", 0)
    invalid_phone = counts.get("invalid_phone", 0)
    successful_calls = max(total_calls - no_answer - invalid_phone, 0)
    appointments = counts.get("appointment_set", 0)
    listed = counts.get("for_sale_set", 0) + counts.get("published", 0)
    rejected = counts.get("rejected", 0)
    thinking = counts.get("thinking", 0)

    return {
        "total_calls": total_calls,
        "successful_calls": successful_calls,
        "appointments": appointments,
        "listed": listed,
        "rejected": rejected,
        "thinking": thinking,
    }


async def daily_stats(manager_id: int) -> dict[str, int]:
    return await stats_for_period(manager_id, 1)


async def weekly_stats(manager_id: int) -> dict[str, int]:
    return await stats_for_period(manager_id, 7)


async def monthly_stats(manager_id: int) -> dict[str, int]:
    return await stats_for_period(manager_id, 30)
