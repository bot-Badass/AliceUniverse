from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ALLOWED_ROLES, User

DENIED_ROLE = "denied"


@dataclass
class UserStats:
    total_users: int
    active_users: int
    pending_users: int


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_or_create_pending(self, telegram_id: int, full_name: str, username: str | None) -> tuple[User, bool]:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            should_notify_admins = False
            if not user.is_active and user.role == DENIED_ROLE:
                # User retries after denial; return to pending queue.
                user.role = None
                should_notify_admins = True
            if user.full_name != full_name or user.username != username:
                user.full_name = full_name
                user.username = username
                should_notify_admins = True
            if should_notify_admins:
                await self.session.commit()
            return user, should_notify_admins

        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
            is_active=False,
            role=None,
            total_donated=0,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user, True

    async def approve_user(self, telegram_id: int, role: str, strict_role: bool = True) -> User | None:
        if strict_role and role not in ALLOWED_ROLES:
            raise ValueError("invalid role")

        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return None

        user.is_active = True
        user.role = role
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def ban_user(self, telegram_id: int) -> User | None:
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return None

        user.is_active = False
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def deny_user(self, telegram_id: int) -> User | None:
        user = await self.get_by_telegram_id(telegram_id)
        if not user:
            return None

        user.is_active = False
        user.role = DENIED_ROLE
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_active_users(self) -> list[User]:
        result = await self.session.execute(select(User).where(User.is_active.is_(True)))
        return list(result.scalars().all())

    async def get_pending_users(self) -> list[User]:
        result = await self.session.execute(
            select(User)
            .where(User.is_active.is_(False))
            .where(User.role.is_(None))
            .order_by(User.joined_at.desc())
        )
        return list(result.scalars().all())

    async def get_stats(self) -> UserStats:
        total_users = await self.session.scalar(select(func.count()).select_from(User))
        active_users = await self.session.scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        )
        pending_users = await self.session.scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(False)).where(User.role.is_(None))
        )
        return UserStats(
            total_users=total_users or 0,
            active_users=active_users or 0,
            pending_users=pending_users or 0,
        )
