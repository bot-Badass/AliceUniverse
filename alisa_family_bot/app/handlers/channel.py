from __future__ import annotations

from aiogram import F, Router
from aiogram.types import ChatJoinRequest, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import get_settings
from app.db import SessionLocal
from app.handlers.admin import notify_admins_about_pending
from app.services.channel_service import ChannelService
from app.services.content_service import ensure_hashtags
from app.services.user_service import UserService

router = Router()
settings = get_settings()


def photo_actions_keyboard(photo_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️", callback_data=f"react:photo:{photo_id}:heart"),
                InlineKeyboardButton(text="👍", callback_data=f"react:photo:{photo_id}:like"),
                InlineKeyboardButton(text="👏", callback_data=f"react:photo:{photo_id}:clap"),
            ],
            [InlineKeyboardButton(text="Підтримати Алісу 🍼", url=settings.donation_url)],
            [InlineKeyboardButton(text="✅ Я задонатив", callback_data="donate:report")],
        ]
    )


@router.chat_join_request(F.chat.id == settings.channel_id)
async def channel_join_request_handler(join_request: ChatJoinRequest) -> None:
    user = join_request.from_user
    async with SessionLocal() as session:
        service = UserService(session)
        db_user, should_notify_admins = await service.get_or_create_pending(
            telegram_id=user.id,
            full_name=user.full_name,
            username=user.username,
        )

    if should_notify_admins:
        await notify_admins_about_pending(join_request.bot, db_user)

    try:
        await join_request.bot.send_message(
            user.id,
            "Ми отримали запит на вступ до каналу 💛\n"
            "Очікуйте підтвердження від адміністраторів.\n"
            "Підказка: натисніть у боті /start, щоб потім отримувати приватні сповіщення 🤗",
        )
    except Exception:
        pass


@router.channel_post(F.chat.id == settings.channel_id, F.photo)
async def channel_photo_handler(message: Message) -> None:
    if not message.photo:
        return

    biggest = message.photo[-1]
    caption = ensure_hashtags(message.caption)
    uploaded_at = message.date

    async with SessionLocal() as session:
        channel_service = ChannelService(session)
        user_service = UserService(session)

        photo = await channel_service.save_photo(
            file_id=biggest.file_id,
            caption=caption,
            uploaded_at=uploaded_at,
        )
        active_users = await user_service.get_active_users()

    notify_caption = "📸 Нове фото Аліси!"
    if caption:
        notify_caption += f"\n\n{caption}"

    for user in active_users:
        try:
            await message.bot.send_photo(
                chat_id=user.telegram_id,
                photo=biggest.file_id,
                caption=notify_caption,
                reply_markup=photo_actions_keyboard(photo.id),
            )
        except Exception:
            continue
