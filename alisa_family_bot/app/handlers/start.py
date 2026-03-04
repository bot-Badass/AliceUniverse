from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup

from app.config import get_settings
from app.db import SessionLocal
from app.handlers.admin import admin_keyboard, notify_admins_about_pending
from app.services.user_service import UserService

router = Router()
settings = get_settings()


def donation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Підтримати Алісу 🍼", url=settings.donation_url)]]
    )


def member_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Мій профіль"), KeyboardButton(text="🏆 Рейтинг донаторів")],
        ],
        resize_keyboard=True,
    )


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    if message.from_user is None:
        return

    if message.from_user.id in settings.super_admins:
        await message.answer(
            "Панель супер-адміна активована.",
            reply_markup=admin_keyboard(),
        )
        return

    async with SessionLocal() as session:
        service = UserService(session)
        user, should_notify_admins = await service.get_or_create_pending(
            telegram_id=message.from_user.id,
            full_name=message.from_user.full_name,
            username=message.from_user.username,
        )

    if user.is_active:
        await message.answer("Ви вже маєте доступ до сповіщень 💛", reply_markup=member_keyboard())
        await message.answer("Підтримати Алісу можна тут:", reply_markup=donation_keyboard())
        return

    if should_notify_admins:
        await notify_admins_about_pending(message.bot, user)
        await message.answer(
            "Дякуємо! Ваша заявка на доступ відправлена 💛\n"
            "Очікуйте підтвердження від адміністраторів.",
        )
        await message.answer("Підтримати Алісу можна тут:", reply_markup=donation_keyboard())
        return

    await message.answer("Ваш запит уже на перевірці. Очікуйте підтвердження.")
    await message.answer("Підтримати Алісу можна тут:", reply_markup=donation_keyboard())
