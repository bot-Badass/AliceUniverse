from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Badge, Donation, MilestoneReaction, MonthlyTopDonator, Photo, Reaction, User

BADGE_ACTIVE_VIEWER = "🏅 Активний глядач"
BADGE_SUPPORTER = "💛 Підтримка Аліси"
BADGE_ALL_SEEN = "👀 Все бачив"
BADGE_FIRST_REACTION = "❤️ Перший фан"
BADGE_REGULAR_REACTOR = "👏 Аплодую"
BADGE_SUPER_FAMILY = "💛 Супер-бабуся"
KYIV_TZ = ZoneInfo("Europe/Kyiv")


class EngagementService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_active_user(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id).where(User.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_user(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def add_or_update_reaction(
        self,
        user_id: int,
        object_type: str,
        object_id: int,
        reaction: str,
    ) -> tuple[Reaction, bool]:
        result = await self.session.execute(
            select(Reaction)
            .where(Reaction.user_id == user_id)
            .where(Reaction.object_type == object_type)
            .where(Reaction.object_id == object_id)
        )
        item = result.scalar_one_or_none()
        created = False
        if item is None:
            item = Reaction(
                user_id=user_id,
                object_type=object_type,
                object_id=object_id,
                reaction=reaction,
            )
            self.session.add(item)
            created = True
        else:
            item.reaction = reaction
        await self.session.commit()
        await self.session.refresh(item)
        return item, created

    async def add_or_update_moment_reaction(self, moment_id: int, user_id: int, reaction: str) -> None:
        result = await self.session.execute(
            select(MilestoneReaction)
            .where(MilestoneReaction.milestone_id == moment_id)
            .where(MilestoneReaction.user_id == user_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            item = MilestoneReaction(milestone_id=moment_id, user_id=user_id, reaction=reaction)
            self.session.add(item)
        else:
            item.reaction = reaction
        await self.session.commit()

    async def add_donation(self, user_id: int, amount: int, currency: str = "UAH") -> Donation | None:
        user_result = await self.session.execute(select(User).where(User.telegram_id == user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            return None

        donation = Donation(user_id=user_id, amount=amount, currency=currency)
        self.session.add(donation)
        user.total_donated = (user.total_donated or 0) + amount
        await self.session.commit()
        await self.session.refresh(donation)
        await self.update_badge(user_id)
        return donation

    async def add_badge(self, user_id: int, badge_type: str, description: str, allow_repeat: bool = False) -> bool:
        if not allow_repeat:
            exists = await self.session.scalar(
                select(func.count())
                .select_from(Badge)
                .where(Badge.user_id == user_id)
                .where(Badge.badge_type == badge_type)
            )
            if exists and exists > 0:
                return False
        self.session.add(Badge(user_id=user_id, badge_type=badge_type, description=description))
        await self.session.commit()
        return True

    async def get_user_badges(self, user_id: int) -> list[Badge]:
        result = await self.session.execute(
            select(Badge).where(Badge.user_id == user_id).order_by(Badge.awarded_at.desc())
        )
        return list(result.scalars().all())

    async def get_profile_data(self, user_id: int) -> tuple[User | None, list[Badge]]:
        user_result = await self.session.execute(select(User).where(User.telegram_id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return None, []
        badges = await self.get_user_badges(user_id)
        return user, badges

    async def get_top_donators_for_month(self, month_start: date) -> list[MonthlyTopDonator]:
        result = await self.session.execute(
            select(MonthlyTopDonator)
            .where(MonthlyTopDonator.month == month_start)
            .order_by(MonthlyTopDonator.amount.desc())
            .limit(3)
        )
        return list(result.scalars().all())

    async def recalculate_monthly_top_donators(self, month_start: date) -> list[MonthlyTopDonator]:
        if month_start.month == 12:
            next_month = date(month_start.year + 1, 1, 1)
        else:
            next_month = date(month_start.year, month_start.month + 1, 1)

        rows = await self.session.execute(
            select(
                Donation.user_id,
                func.coalesce(func.sum(Donation.amount), 0).label("total"),
            )
            .where(Donation.timestamp >= month_start)
            .where(Donation.timestamp < next_month)
            .group_by(Donation.user_id)
            .order_by(func.sum(Donation.amount).desc())
            .limit(3)
        )
        top = rows.all()

        await self.session.execute(delete(MonthlyTopDonator).where(MonthlyTopDonator.month == month_start))
        for row in top:
            self.session.add(
                MonthlyTopDonator(
                    month=month_start,
                    user_id=int(row.user_id),
                    amount=int(row.total or 0),
                )
            )
        await self.session.commit()
        return await self.get_top_donators_for_month(month_start)

    async def update_badge(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return None

        donation_total = user.total_donated or 0

        reaction_count = await self.session.scalar(
            select(func.count())
            .select_from(Reaction)
            .where(Reaction.user_id == user_id)
        )
        reaction_count = reaction_count or 0

        total_photos = await self.session.scalar(select(func.count()).select_from(Photo))
        reacted_photos = await self.session.scalar(
            select(func.count())
            .select_from(Reaction)
            .where(Reaction.user_id == user_id)
            .where(Reaction.object_type == "photo")
        )
        total_photos = total_photos or 0
        reacted_photos = reacted_photos or 0

        month_start = date.today().replace(day=1)
        regular_month_reactions = await self.session.scalar(
            select(func.count())
            .select_from(Reaction)
            .where(Reaction.user_id == user_id)
            .where(Reaction.timestamp >= month_start)
        )
        regular_month_reactions = regular_month_reactions or 0

        if total_photos > 0 and reacted_photos >= total_photos:
            user.badge = BADGE_ALL_SEEN
            await self.add_badge(user_id, "all_photos_seen", "Переглянув і відреагував на всі фото")
        elif donation_total >= 100:
            user.badge = BADGE_SUPPORTER
            await self.add_badge(user_id, "supporter", "Сукупний донат понад 100 UAH")
        elif reaction_count >= 1:
            user.badge = BADGE_ACTIVE_VIEWER
            await self.add_badge(user_id, "first_reaction", "Перша реакція на фото або подію")

        if regular_month_reactions >= 5:
            await self.add_badge(user_id, "regular_reactor", "5+ реакцій за місяць")
        if donation_total >= 100 and reaction_count >= 5:
            await self.add_badge(user_id, "super_family", "Підтримує донатами і активно реагує")

        await self.session.commit()
        await self.session.refresh(user)
        return user


def month_start_utc(today: datetime | None = None) -> date:
    base = (today or datetime.now(timezone.utc)).astimezone(KYIV_TZ)
    return date(base.year, base.month, 1)
