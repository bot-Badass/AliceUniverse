from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InputMediaPhoto

from app.config import get_settings
from app.db import SessionLocal
from app.services.engagement_service import EngagementService, month_start_utc
from app.services.growth_service import GrowthService
from app.services.channel_service import ScheduledPostService

settings = get_settings()
logger = logging.getLogger(__name__)
LAST_WEEKLY_REMINDER: date | None = None
LAST_MONTHLY_REMINDER: date | None = None
LAST_MONTHLY_TOP: date | None = None
KYIV_TZ = ZoneInfo("Europe/Kyiv")


async def requeue_processing_posts() -> int:
    async with SessionLocal() as session:
        service = ScheduledPostService(session)
        return await service.requeue_processing_posts()


async def process_due_posts(bot: Bot) -> int:
    now_utc = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        service = ScheduledPostService(session)
        due_posts = await service.claim_due_posts(now_utc=now_utc, limit=20)

    if not due_posts:
        return 0

    processed = 0
    for post in due_posts:
        try:
            media_type, file_ids = decode_scheduled_media_ref(post.file_id)
            await publish_scheduled_media(
                bot=bot,
                media_type=media_type,
                file_ids=file_ids,
                caption=post.caption or None,
            )
            async with SessionLocal() as session:
                service = ScheduledPostService(session)
                await service.mark_published(post.id, datetime.now(timezone.utc))
            processed += 1
        except Exception as exc:
            async with SessionLocal() as session:
                service = ScheduledPostService(session)
                await service.mark_failed(post.id, str(exc))
            logger.exception("Failed to publish scheduled post id=%s", post.id)

    return processed


def decode_scheduled_media_ref(raw: str) -> tuple[str, list[str]]:
    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
            media_type = payload.get("type", "photo")
            ids = payload.get("ids") or []
            ids = [str(x) for x in ids if x]
            if ids:
                return media_type, ids
        except Exception:
            pass
    return "photo", [raw]


async def publish_scheduled_media(
    bot: Bot,
    media_type: str,
    file_ids: list[str],
    caption: str | None,
) -> None:
    if not file_ids:
        await bot.send_message(settings.channel_id, caption or "Оновлення без медіа")
        return
    if media_type == "video":
        await bot.send_video(chat_id=settings.channel_id, video=file_ids[0], caption=caption or None)
        return
    if len(file_ids) == 1:
        await bot.send_photo(chat_id=settings.channel_id, photo=file_ids[0], caption=caption or None)
        return
    media = []
    for idx, fid in enumerate(file_ids):
        media.append(InputMediaPhoto(media=fid, caption=caption if idx == 0 else None))
    await bot.send_media_group(chat_id=settings.channel_id, media=media)


async def scheduler_worker(bot: Bot, interval_seconds: int = 10) -> None:
    requeued = await requeue_processing_posts()
    if requeued:
        logger.info("Requeued %s processing scheduled posts after startup", requeued)

    while True:
        try:
            await process_due_posts(bot)
            await process_growth_reminders(bot)
            await process_monthly_top_donators(bot)
        except Exception:
            logger.exception("Scheduler worker iteration failed")
        await asyncio.sleep(interval_seconds)


async def process_growth_reminders(bot: Bot) -> None:
    global LAST_WEEKLY_REMINDER, LAST_MONTHLY_REMINDER

    today = datetime.now(timezone.utc).astimezone(KYIV_TZ).date()

    if today.weekday() == 0 and LAST_WEEKLY_REMINDER != today:
        async with SessionLocal() as session:
            growth = GrowthService(session)
            if await growth.needs_weight_reminder():
                for admin_id in settings.super_admins:
                    try:
                        await bot.send_message(
                            admin_id,
                            "🔔 Нагадування: час зафіксувати вагу Аліси цього тижня (⚖️).",
                        )
                    except Exception:
                        continue
        LAST_WEEKLY_REMINDER = today

    if today.day == 1 and LAST_MONTHLY_REMINDER != today:
        async with SessionLocal() as session:
            growth = GrowthService(session)
            if await growth.needs_height_reminder():
                for admin_id in settings.super_admins:
                    try:
                        await bot.send_message(
                            admin_id,
                            "🔔 Нагадування: час оновити зріст Аліси цього місяця (📏).",
                        )
                    except Exception:
                        continue
        LAST_MONTHLY_REMINDER = today


async def process_monthly_top_donators(bot: Bot) -> None:
    global LAST_MONTHLY_TOP
    today = datetime.now(timezone.utc).astimezone(KYIV_TZ).date()
    if today.day != 1 or LAST_MONTHLY_TOP == today:
        return

    month_start = month_start_utc(datetime.now(timezone.utc))
    async with SessionLocal() as session:
        service = EngagementService(session)
        top = await service.recalculate_monthly_top_donators(month_start)

        if not top:
            LAST_MONTHLY_TOP = today
            return

        labels = ["🥇", "🥈", "🥉"]
        names: list[str] = []
        for i, row in enumerate(top[:3]):
            user = await service.get_user(row.user_id)
            name = user.full_name if user else str(row.user_id)
            names.append(f"{labels[i]} {name}")

            badge_type = f"top_donor_{i + 1}"
            await service.add_badge(
                row.user_id,
                badge_type,
                f"Топ-{i + 1} донатор за {month_start.strftime('%m.%Y')}",
                allow_repeat=True,
            )
            try:
                await bot.send_message(
                    row.user_id,
                    f"🎉 Вітаємо! Ви {labels[i]} донатор місяця для Аліси 💛",
                )
            except Exception:
                pass

    text = "💛 Топ-донатори місяця 💛\n\n" + "\n".join(names) + "\n\nДякуємо всім за підтримку Аліси! 🍼"
    try:
        await bot.send_message(settings.channel_id, text)
    except Exception:
        pass
    LAST_MONTHLY_TOP = today
