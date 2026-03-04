from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Photo, ScheduledPost


class ChannelService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_photo(
        self,
        file_id: str,
        caption: str | None,
        uploaded_at: datetime,
        month_number: int | None = None,
    ) -> Photo:
        photo = Photo(
            file_id=file_id,
            caption=caption,
            uploaded_at=uploaded_at,
            month_number=month_number,
        )
        self.session.add(photo)
        await self.session.commit()
        await self.session.refresh(photo)
        return photo


class ScheduledPostService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_scheduled_post(
        self,
        file_id: str,
        caption: str | None,
        publish_at: datetime,
        created_by_telegram_id: int,
    ) -> ScheduledPost:
        post = ScheduledPost(
            file_id=file_id,
            caption=caption,
            publish_at=publish_at,
            status="pending",
            created_by_telegram_id=created_by_telegram_id,
        )
        self.session.add(post)
        await self.session.commit()
        await self.session.refresh(post)
        return post

    async def requeue_processing_posts(self) -> int:
        result = await self.session.execute(
            select(ScheduledPost).where(ScheduledPost.status == "processing")
        )
        items = list(result.scalars().all())
        for item in items:
            item.status = "pending"
            item.error_message = None
        await self.session.commit()
        return len(items)

    async def claim_due_posts(self, now_utc: datetime, limit: int = 20) -> list[ScheduledPost]:
        result = await self.session.execute(
            select(ScheduledPost)
            .where(ScheduledPost.status == "pending")
            .where(ScheduledPost.publish_at <= now_utc)
            .order_by(ScheduledPost.publish_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        posts = list(result.scalars().all())
        for post in posts:
            post.status = "processing"
            post.error_message = None
        await self.session.commit()
        return posts

    async def mark_published(self, post_id: int, now_utc: datetime) -> None:
        result = await self.session.execute(select(ScheduledPost).where(ScheduledPost.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            return
        post.status = "published"
        post.published_at = now_utc
        post.error_message = None
        await self.session.commit()

    async def mark_failed(self, post_id: int, error_message: str) -> None:
        result = await self.session.execute(select(ScheduledPost).where(ScheduledPost.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            return
        post.status = "failed"
        post.error_message = error_message[:1000]
        await self.session.commit()

    async def get_pending_scheduled_posts(self, limit: int = 100) -> list[ScheduledPost]:
        result = await self.session.execute(
            select(ScheduledPost)
            .where(ScheduledPost.status == "pending")
            .order_by(ScheduledPost.publish_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def cancel_pending_post(self, post_id: int) -> bool:
        result = await self.session.execute(select(ScheduledPost).where(ScheduledPost.id == post_id))
        post = result.scalar_one_or_none()
        if not post or post.status != "pending":
            return False
        post.status = "canceled"
        post.error_message = None
        await self.session.commit()
        return True
