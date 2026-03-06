from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MorningSession, MorningStepLog, MorningStreak


class MorningService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_session(self, user_id: int) -> MorningSession | None:
        result = await self.session.execute(
            select(MorningSession)
            .where(MorningSession.user_id == user_id)
            .where(MorningSession.status == "active")
            .order_by(MorningSession.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def start_session(self, user_id: int) -> MorningSession:
        existing = await self.get_active_session(user_id)
        if existing:
            return existing

        session = MorningSession(user_id=user_id, status="active", completed_steps=0)
        self.session.add(session)
        await self.session.commit()
        await self.session.refresh(session)
        return session

    async def start_step(self, session_id: int, step_key: str) -> MorningStepLog:
        item = MorningStepLog(session_id=session_id, step_key=step_key, status="started")
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def complete_step(self, session_id: int, step_key: str, payload: str | None = None) -> None:
        result = await self.session.execute(
            select(MorningStepLog)
            .where(MorningStepLog.session_id == session_id)
            .where(MorningStepLog.step_key == step_key)
            .order_by(MorningStepLog.started_at.desc())
            .limit(1)
        )
        item = result.scalar_one_or_none()
        if item is None:
            item = MorningStepLog(session_id=session_id, step_key=step_key, status="done", payload=payload)
            self.session.add(item)
        else:
            item.status = "done"
            item.payload = payload
            item.completed_at = datetime.now(timezone.utc)

        session_result = await self.session.execute(select(MorningSession).where(MorningSession.id == session_id))
        session = session_result.scalar_one_or_none()
        if session:
            done_count = await self.session.scalar(
                select(func.count())
                .select_from(MorningStepLog)
                .where(MorningStepLog.session_id == session_id)
                .where(MorningStepLog.status == "done")
            )
            session.completed_steps = int(done_count or 0)

        await self.session.commit()

    async def skip_step(self, session_id: int, step_key: str) -> None:
        item = MorningStepLog(session_id=session_id, step_key=step_key, status="skipped")
        self.session.add(item)
        await self.session.commit()

    async def finish_session(self, session_id: int, status: str = "done") -> MorningSession | None:
        result = await self.session.execute(select(MorningSession).where(MorningSession.id == session_id))
        session = result.scalar_one_or_none()
        if session is None:
            return None

        session.status = status
        session.finished_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(session)

        if status == "done":
            await self.update_streak(session.user_id)

        return session

    async def update_streak(self, user_id: int) -> MorningStreak:
        result = await self.session.execute(select(MorningStreak).where(MorningStreak.user_id == user_id))
        streak = result.scalar_one_or_none()
        today = datetime.now(timezone.utc).date()

        if streak is None:
            streak = MorningStreak(user_id=user_id, current_streak=1, best_streak=1, last_completed_date=today)
            self.session.add(streak)
            await self.session.commit()
            await self.session.refresh(streak)
            return streak

        if streak.last_completed_date == today:
            return streak

        if streak.last_completed_date == today - timedelta(days=1):
            streak.current_streak += 1
        else:
            streak.current_streak = 1

        streak.last_completed_date = today
        streak.best_streak = max(streak.best_streak, streak.current_streak)
        await self.session.commit()
        await self.session.refresh(streak)
        return streak

    async def get_streak(self, user_id: int) -> MorningStreak | None:
        result = await self.session.execute(select(MorningStreak).where(MorningStreak.user_id == user_id))
        return result.scalar_one_or_none()
