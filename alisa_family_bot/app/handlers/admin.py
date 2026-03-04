from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import func, select
from aiogram.types import (
    CallbackQuery,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from app.config import get_settings
from app.db import SessionLocal
from app.models import Donation, MemorableMoment, ScheduledPost, User
from app.services.channel_service import ScheduledPostService
from app.services.content_service import ensure_hashtags, extract_hashtags
from app.services.growth_service import GrowthService
from app.services.moment_service import MemorableMomentService
from app.services.user_service import UserService

router = Router()
settings = get_settings()
KYIV_TZ = ZoneInfo("Europe/Kyiv")

BTN_PENDING = "🕓 Очікують підтвердження"
BTN_NEW_POST = "🆕 Новий пост"
BTN_ADD_MOMENT = "✨ Додати памʼятний момент"
BTN_GROWTH = "📈 Календар розвитку"
BTN_SCHEDULED = "🧾 Заплановані пости"
BTN_STATS = "📊 Статистика"
BTN_CANCEL = "❌ Скасувати"
BTN_SKIP_CAPTION = "➡️ Без опису"
BTN_SKIP_DESCRIPTION = "➡️ Без опису"
BTN_SKIP_MEDIA = "➡️ Без фото/відео"
BTN_MEDIA_DONE = "✅ Готово"
BTN_TODAY = "📅 Сьогодні"
BTN_AUTO_HASHTAGS = "🏷 Автохештеги"
BTN_CUSTOM_ROLE = "✍️ Ввести роль вручну"
BTN_GROWTH_WEIGHT = "⚖️ Додати вагу"
BTN_GROWTH_HEIGHT = "📏 Додати зріст"
BTN_GROWTH_EVENT = "👶 Подія (зуб/кроки/звіт)"

ROLE_KEY_TO_LABEL = {
    "mama": "мама",
    "tato": "тато",
    "babusia": "бабуся",
    "didus": "дідусь",
    "prababusia": "прабабуся",
    "pradidus": "прадідусь",
    "dyadko": "дядько",
    "titka": "тітка",
    "hreshena": "хрещена",
    "hreshenyy": "хрещений",
}


class AdminStates(StatesGroup):
    waiting_post_photo = State()
    waiting_post_caption = State()
    waiting_post_schedule_choice = State()
    waiting_post_datetime = State()
    waiting_moment_title = State()
    waiting_moment_description = State()
    waiting_moment_media = State()
    waiting_moment_date = State()
    waiting_moment_hashtags = State()
    waiting_custom_role = State()
    waiting_growth_value = State()
    waiting_growth_event_title = State()
    waiting_growth_event_note = State()


def is_super_admin_message(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in settings.super_admins)


def is_super_admin_callback(callback: CallbackQuery) -> bool:
    return bool(callback.from_user and callback.from_user.id in settings.super_admins)


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PENDING), KeyboardButton(text=BTN_NEW_POST)],
            [KeyboardButton(text=BTN_ADD_MOMENT), KeyboardButton(text=BTN_GROWTH)],
            [KeyboardButton(text=BTN_SCHEDULED), KeyboardButton(text=BTN_STATS)],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def caption_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SKIP_CAPTION)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def post_media_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_MEDIA_DONE)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def moment_description_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SKIP_DESCRIPTION)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def moment_media_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_MEDIA_DONE)],
            [KeyboardButton(text=BTN_SKIP_MEDIA)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def moment_date_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_TODAY)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def moment_hashtag_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_AUTO_HASHTAGS)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def growth_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_GROWTH_WEIGHT), KeyboardButton(text=BTN_GROWTH_HEIGHT)],
            [KeyboardButton(text=BTN_GROWTH_EVENT)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def moment_actions_keyboard(moment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️", callback_data=f"react:moment:{moment_id}:heart"),
                InlineKeyboardButton(text="👍", callback_data=f"react:moment:{moment_id}:like"),
                InlineKeyboardButton(text="👏", callback_data=f"react:moment:{moment_id}:clap"),
            ],
            [InlineKeyboardButton(text="Підтримати Алісу 🍼", url=settings.donation_url)],
            [InlineKeyboardButton(text="✅ Я задонатив", callback_data="donate:report")],
        ]
    )


def pending_actions_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"approve:{telegram_id}:0"),
                InlineKeyboardButton(text="❌ Відхилити", callback_data=f"deny:{telegram_id}:0"),
            ],
            [InlineKeyboardButton(text="📚 Відкрити список заявок", callback_data="pending:view:0")],
        ]
    )


def roles_keyboard(telegram_id: int, index: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=role_label.capitalize(), callback_data=f"role:{telegram_id}:{role_key}:{index}"
        )
        for role_key, role_label in ROLE_KEY_TO_LABEL.items()
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i : i + 2])
    rows.append([InlineKeyboardButton(text=BTN_CUSTOM_ROLE, callback_data=f"rolecustom:{telegram_id}:{index}")])
    rows.append([InlineKeyboardButton(text="↩️ Назад до заявок", callback_data=f"pending:view:{index}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def empty_pending_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔄 Оновити", callback_data="pending:view:0")]]
    )


def pending_card_keyboard(telegram_id: int, index: int, total: int) -> InlineKeyboardMarkup:
    if total <= 1:
        prev_idx = 0
        next_idx = 0
    else:
        prev_idx = (index - 1) % total
        next_idx = (index + 1) % total

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"approve:{telegram_id}:{index}"),
                InlineKeyboardButton(text="❌ Відхилити", callback_data=f"deny:{telegram_id}:{index}"),
            ],
            [
                InlineKeyboardButton(text="⬅️", callback_data=f"pending:view:{prev_idx}"),
                InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="pending:noop"),
                InlineKeyboardButton(text="➡️", callback_data=f"pending:view:{next_idx}"),
            ],
            [InlineKeyboardButton(text="🔄 Оновити", callback_data=f"pending:view:{index}")],
        ]
    )


def publish_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ Опублікувати зараз", callback_data="post:now"),
                InlineKeyboardButton(text="🗓 Запланувати", callback_data="post:later"),
            ]
        ]
    )


def empty_scheduled_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔄 Оновити", callback_data="sched:view:0")]]
    )


def scheduled_card_keyboard(post_id: int, index: int, total: int) -> InlineKeyboardMarkup:
    if total <= 1:
        prev_idx = 0
        next_idx = 0
    else:
        prev_idx = (index - 1) % total
        next_idx = (index + 1) % total

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Скасувати пост", callback_data=f"sched:cancel:{post_id}:{index}")],
            [
                InlineKeyboardButton(text="⬅️", callback_data=f"sched:view:{prev_idx}"),
                InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="sched:noop"),
                InlineKeyboardButton(text="➡️", callback_data=f"sched:view:{next_idx}"),
            ],
            [InlineKeyboardButton(text="🔄 Оновити", callback_data=f"sched:view:{index}")],
        ]
    )


def parse_publish_datetime(raw: str) -> datetime | None:
    value = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=KYIV_TZ)
        except ValueError:
            continue
    return None


def parse_moment_date(raw: str) -> date | None:
    value = raw.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def pending_user_text(user: User) -> str:
    username = f"@{user.username}" if user.username else "-"
    joined_at = user.joined_at
    if joined_at.tzinfo is None:
        joined_at = joined_at.replace(tzinfo=timezone.utc)
    joined = joined_at.astimezone(KYIV_TZ).strftime("%d.%m.%Y %H:%M")
    return (
        "Нова заявка на доступ 💛\n"
        f"ID: <code>{user.telegram_id}</code>\n"
        f"Ім'я: {user.full_name}\n"
        f"Username: {username}\n"
        f"Заявка: {joined} (Europe/Kyiv)"
    )


def pending_user_card_text(user: User, index: int, total: int) -> str:
    return f"Картка заявки {index + 1}/{total}\n\n{pending_user_text(user)}"


def scheduled_post_card_text(post: ScheduledPost, index: int, total: int) -> str:
    publish_local = post.publish_at.astimezone(KYIV_TZ).strftime("%d.%m.%Y %H:%M")
    caption_preview = (post.caption or "Без опису").strip()
    if len(caption_preview) > 120:
        caption_preview = caption_preview[:117] + "..."
    return (
        f"Запланований пост {index + 1}/{total}\n\n"
        f"ID: <code>{post.id}</code>\n"
        f"Публікація: {publish_local} (Europe/Kyiv)\n"
        f"Автор ID: <code>{post.created_by_telegram_id}</code>\n"
        f"Опис: {caption_preview}"
    )


def memorable_moment_text(title: str, description: str | None, moment_date: date, hashtags: str) -> str:
    description_text = description or "Без опису"
    return (
        f"🎉 Новий памʼятний момент: {title}\n"
        f"{description_text}\n"
        f"Дата: {moment_date.strftime('%d.%m.%Y')}\n\n"
        f"{hashtags}"
    )


def welcome_channel_text(role: str, full_name: str) -> str:
    role_text = role.capitalize()
    return (
        f"✨ {role_text} {full_name} приєднав(лася) до Маленького Всесвіту Аліси!\n"
        "Ласкаво просимо в нашу теплу родинну спільноту 💛👶\n"
        "Щоб отримувати особисті сповіщення, відкрийте бота і натисніть /start 🤗"
    )


async def load_pending_users() -> list[User]:
    async with SessionLocal() as session:
        service = UserService(session)
        return await service.get_pending_users()


async def load_scheduled_posts() -> list[ScheduledPost]:
    async with SessionLocal() as session:
        service = ScheduledPostService(session)
        return await service.get_pending_scheduled_posts(limit=100)


async def show_pending_card_in_message(message: Message, index: int = 0) -> None:
    pending_users = await load_pending_users()
    if not pending_users:
        await message.answer("Заявок в очікуванні немає.", reply_markup=empty_pending_keyboard())
        return

    normalized_index = min(max(index, 0), len(pending_users) - 1)
    user = pending_users[normalized_index]
    await message.answer(
        pending_user_card_text(user, normalized_index, len(pending_users)),
        reply_markup=pending_card_keyboard(user.telegram_id, normalized_index, len(pending_users)),
    )


async def show_pending_card_in_callback(callback: CallbackQuery, index: int, toast: str | None = None) -> None:
    if not callback.message:
        return

    pending_users = await load_pending_users()
    if not pending_users:
        try:
            await callback.message.edit_text("Заявок в очікуванні немає.", reply_markup=empty_pending_keyboard())
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc):
                raise
        await callback.answer(toast or "Список оновлено")
        return

    normalized_index = min(max(index, 0), len(pending_users) - 1)
    user = pending_users[normalized_index]
    try:
        await callback.message.edit_text(
            pending_user_card_text(user, normalized_index, len(pending_users)),
            reply_markup=pending_card_keyboard(user.telegram_id, normalized_index, len(pending_users)),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
    await callback.answer(toast or "Оновлено")


async def show_scheduled_card_in_message(message: Message, index: int = 0) -> None:
    posts = await load_scheduled_posts()
    if not posts:
        await message.answer("Немає запланованих постів.", reply_markup=empty_scheduled_keyboard())
        return

    normalized_index = min(max(index, 0), len(posts) - 1)
    post = posts[normalized_index]
    await message.answer(
        scheduled_post_card_text(post, normalized_index, len(posts)),
        reply_markup=scheduled_card_keyboard(post.id, normalized_index, len(posts)),
    )


async def show_scheduled_card_in_callback(callback: CallbackQuery, index: int, toast: str | None = None) -> None:
    if not callback.message:
        return

    posts = await load_scheduled_posts()
    if not posts:
        try:
            await callback.message.edit_text("Немає запланованих постів.", reply_markup=empty_scheduled_keyboard())
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc):
                raise
        await callback.answer(toast or "Список оновлено")
        return

    normalized_index = min(max(index, 0), len(posts) - 1)
    post = posts[normalized_index]
    try:
        await callback.message.edit_text(
            scheduled_post_card_text(post, normalized_index, len(posts)),
            reply_markup=scheduled_card_keyboard(post.id, normalized_index, len(posts)),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
    await callback.answer(toast or "Оновлено")


async def notify_admins_about_pending(bot, user: User) -> None:
    text = pending_user_text(user)
    keyboard = pending_actions_keyboard(user.telegram_id)
    for admin_id in settings.super_admins:
        try:
            await bot.send_message(admin_id, text, reply_markup=keyboard)
        except Exception:
            continue


async def publish_to_channel(bot, file_id: str, caption: str | None) -> None:
    await publish_media(
        bot=bot,
        chat_id=settings.channel_id,
        media_type="photo",
        file_ids=[file_id],
        caption=caption,
    )


def encode_scheduled_media_ref(media_type: str, file_ids: list[str]) -> str:
    return json.dumps({"type": media_type, "ids": file_ids}, ensure_ascii=False)


async def publish_media(
    bot,
    chat_id: int,
    media_type: str,
    file_ids: list[str],
    caption: str | None,
) -> None:
    if not file_ids:
        await bot.send_message(chat_id=chat_id, text=caption or "Оновлення без медіа")
        return

    if media_type == "video":
        await bot.send_video(chat_id=chat_id, video=file_ids[0], caption=caption or None)
        return

    if len(file_ids) == 1:
        await bot.send_photo(chat_id=chat_id, photo=file_ids[0], caption=caption or None)
        return

    media_group = []
    for idx, fid in enumerate(file_ids):
        media_group.append(
            InputMediaPhoto(
                media=fid,
                caption=caption if idx == 0 else None,
            )
        )
    await bot.send_media_group(chat_id=chat_id, media=media_group)


async def broadcast_memorable_moment(
    bot,
    title: str,
    description: str | None,
    moment_date: date,
    hashtags_text: str,
    media_type: str | None,
    media_file_ids: list[str] | None,
    moment_id: int,
) -> int:
    text = memorable_moment_text(title, description, moment_date, hashtags_text)
    keyboard = moment_actions_keyboard(moment_id)
    media_file_ids = media_file_ids or []

    try:
        if media_type == "photo" and len(media_file_ids) > 1:
            await publish_media(
                bot=bot,
                chat_id=settings.channel_id,
                media_type="photo",
                file_ids=media_file_ids,
                caption=None,
            )
            await bot.send_message(chat_id=settings.channel_id, text=text, reply_markup=keyboard)
        elif media_type == "photo" and media_file_ids:
            await bot.send_photo(
                chat_id=settings.channel_id,
                photo=media_file_ids[0],
                caption=text,
                reply_markup=keyboard,
            )
        elif media_type == "video" and media_file_ids:
            await bot.send_video(chat_id=settings.channel_id, video=media_file_ids[0], caption=text, reply_markup=keyboard)
        else:
            await bot.send_message(chat_id=settings.channel_id, text=text, reply_markup=keyboard)
    except Exception:
        pass

    async with SessionLocal() as session:
        service = UserService(session)
        users = await service.get_active_users()

    sent = 0
    for user in users:
        try:
            if media_type == "photo" and len(media_file_ids) > 1:
                await publish_media(
                    bot=bot,
                    chat_id=user.telegram_id,
                    media_type="photo",
                    file_ids=media_file_ids,
                    caption=None,
                )
                await bot.send_message(chat_id=user.telegram_id, text=text, reply_markup=keyboard)
            elif media_type == "photo" and media_file_ids:
                await bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=media_file_ids[0],
                    caption=text,
                    reply_markup=keyboard,
                )
            elif media_type == "video" and media_file_ids:
                await bot.send_video(
                    chat_id=user.telegram_id,
                    video=media_file_ids[0],
                    caption=text,
                    reply_markup=keyboard,
                )
            else:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    reply_markup=keyboard,
                )
            sent += 1
        except Exception:
            continue
    return sent


@router.message(F.text == BTN_CANCEL)
async def cancel_flow(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    await state.clear()
    await message.answer("Дію скасовано.", reply_markup=admin_keyboard())


@router.message(F.text == BTN_PENDING)
async def pending_list_handler(message: Message) -> None:
    if not is_super_admin_message(message):
        return

    await message.answer("Панель заявок:", reply_markup=admin_keyboard())
    await show_pending_card_in_message(message, index=0)


@router.callback_query(F.data == "pending:noop")
async def pending_noop_handler(callback: CallbackQuery) -> None:
    if not is_super_admin_callback(callback):
        return
    await callback.answer()


@router.callback_query(F.data.startswith("pending:view:"))
async def pending_view_handler(callback: CallbackQuery) -> None:
    if not is_super_admin_callback(callback):
        return
    if not callback.data:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Невірний формат", show_alert=True)
        return

    try:
        index = int(parts[2])
    except ValueError:
        await callback.answer("Невірний індекс", show_alert=True)
        return

    await show_pending_card_in_callback(callback, index=index)


@router.message(F.text == BTN_SCHEDULED)
async def scheduled_posts_handler(message: Message) -> None:
    if not is_super_admin_message(message):
        return

    await message.answer("Панель запланованих постів:", reply_markup=admin_keyboard())
    await show_scheduled_card_in_message(message, index=0)


@router.callback_query(F.data == "sched:noop")
async def scheduled_noop_handler(callback: CallbackQuery) -> None:
    if not is_super_admin_callback(callback):
        return
    await callback.answer()


@router.callback_query(F.data.startswith("sched:view:"))
async def scheduled_view_handler(callback: CallbackQuery) -> None:
    if not is_super_admin_callback(callback):
        return
    if not callback.data:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Невірний формат", show_alert=True)
        return

    try:
        index = int(parts[2])
    except ValueError:
        await callback.answer("Невірний індекс", show_alert=True)
        return

    await show_scheduled_card_in_callback(callback, index=index)


@router.callback_query(F.data.startswith("sched:cancel:"))
async def scheduled_cancel_handler(callback: CallbackQuery) -> None:
    if not is_super_admin_callback(callback):
        return
    if not callback.data:
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Невірний формат", show_alert=True)
        return

    try:
        post_id = int(parts[2])
        index = int(parts[3])
    except ValueError:
        await callback.answer("Невірний ID", show_alert=True)
        return

    async with SessionLocal() as session:
        service = ScheduledPostService(session)
        canceled = await service.cancel_pending_post(post_id)

    if not canceled:
        await show_scheduled_card_in_callback(callback, index=index, toast="Пост вже не активний")
        return

    await show_scheduled_card_in_callback(callback, index=index, toast="Пост скасовано")


@router.callback_query(F.data.startswith("approve:"))
async def approve_request_handler(callback: CallbackQuery) -> None:
    if not is_super_admin_callback(callback):
        return
    if not callback.data or not callback.message:
        return

    parts = callback.data.split(":")
    if len(parts) not in {2, 3}:
        await callback.answer("Невірний формат", show_alert=True)
        return

    telegram_id_raw = parts[1]
    index_raw = parts[2] if len(parts) == 3 else "0"
    try:
        telegram_id = int(telegram_id_raw)
        index = int(index_raw)
    except ValueError:
        await callback.answer("Невірний ID", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=roles_keyboard(telegram_id, index))
    await callback.answer("Оберіть роль")


@router.callback_query(F.data.startswith("deny:"))
async def deny_request_handler(callback: CallbackQuery) -> None:
    if not is_super_admin_callback(callback):
        return
    if not callback.data:
        return

    parts = callback.data.split(":")
    if len(parts) not in {2, 3}:
        await callback.answer("Невірний формат", show_alert=True)
        return

    telegram_id_raw = parts[1]
    index_raw = parts[2] if len(parts) == 3 else "0"
    try:
        telegram_id = int(telegram_id_raw)
        index = int(index_raw)
    except ValueError:
        await callback.answer("Невірний ID", show_alert=True)
        return

    async with SessionLocal() as session:
        service = UserService(session)
        user = await service.deny_user(telegram_id)

    if not user:
        await callback.answer("Користувача не знайдено", show_alert=True)
        return

    try:
        await callback.bot.decline_chat_join_request(chat_id=settings.channel_id, user_id=telegram_id)
    except Exception:
        pass

    try:
        await callback.bot.send_message(
            telegram_id,
            "На жаль, заявку на доступ поки не підтверджено. Можете спробувати пізніше.",
        )
    except Exception:
        pass

    await show_pending_card_in_callback(callback, index=index, toast="Заявку відхилено")


async def approve_user_with_role(
    bot,
    telegram_id: int,
    role: str,
) -> User | None:
    async with SessionLocal() as session:
        service = UserService(session)
        user = await service.approve_user(telegram_id=telegram_id, role=role, strict_role=False)

    if not user:
        return None

    try:
        await bot.approve_chat_join_request(chat_id=settings.channel_id, user_id=telegram_id)
    except Exception:
        pass

    try:
        await bot.send_message(
            settings.channel_id,
            welcome_channel_text(role=role, full_name=user.full_name),
        )
    except Exception:
        pass

    try:
        await bot.send_message(
            telegram_id,
            "Ваш доступ до каналу надано 💛\n"
            "Щоб отримувати приватні сповіщення про нові фото і події, перейдіть у бота та натисніть /start 🤗",
        )
    except Exception:
        pass

    return user


@router.callback_query(F.data.startswith("role:"))
async def approve_with_role_handler(callback: CallbackQuery) -> None:
    if not is_super_admin_callback(callback):
        return
    if not callback.data:
        return

    parts = callback.data.split(":")
    if len(parts) not in {3, 4}:
        await callback.answer("Невірний формат", show_alert=True)
        return

    telegram_id_raw = parts[1]
    role_key = parts[2]
    index_raw = parts[3] if len(parts) == 4 else "0"
    role = ROLE_KEY_TO_LABEL.get(role_key)
    if role is None:
        await callback.answer("Невідома роль", show_alert=True)
        return

    try:
        telegram_id = int(telegram_id_raw)
        index = int(index_raw)
    except ValueError:
        await callback.answer("Невірний ID", show_alert=True)
        return

    user = await approve_user_with_role(bot=callback.bot, telegram_id=telegram_id, role=role)
    if not user:
        await callback.answer("Користувача не знайдено", show_alert=True)
        return
    await show_pending_card_in_callback(callback, index=index, toast=f"Підтверджено ({role})")


@router.callback_query(F.data.startswith("rolecustom:"))
async def custom_role_entry_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_super_admin_callback(callback):
        return
    if not callback.data or not callback.message:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Невірний формат", show_alert=True)
        return

    try:
        telegram_id = int(parts[1])
        index = int(parts[2])
    except ValueError:
        await callback.answer("Невірний ID", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_custom_role)
    await state.update_data(custom_role_telegram_id=telegram_id, custom_role_index=index)
    await callback.answer()
    await callback.message.answer("Введіть роль вручну (наприклад: хрещена мама).")


@router.message(AdminStates.waiting_custom_role)
async def custom_role_submit_handler(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    if not message.text:
        await message.answer("Надішліть роль текстом.")
        return
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return

    data = await state.get_data()
    telegram_id = data.get("custom_role_telegram_id")
    index = data.get("custom_role_index", 0)
    if not isinstance(telegram_id, int):
        await state.clear()
        await message.answer("Не знайдено заявку. Спробуйте ще раз.", reply_markup=admin_keyboard())
        return

    role = message.text.strip()
    if not role:
        await message.answer("Роль не може бути порожньою.")
        return

    await state.clear()

    user = await approve_user_with_role(bot=message.bot, telegram_id=telegram_id, role=role)
    if not user:
        await message.answer("Користувача не знайдено.", reply_markup=admin_keyboard())
        return
    await message.answer(f"✅ Користувача підтверджено з роллю: {role}", reply_markup=admin_keyboard())
    await message.answer("Підказка: у панелі заявок натисніть 🔄 Оновити, щоб прибрати оброблену заявку.")


@router.message(F.text == BTN_ADD_MOMENT)
async def add_memorable_moment_entry(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    await state.set_state(AdminStates.waiting_moment_title)
    await message.answer("Введіть назву памʼятного моменту.", reply_markup=cancel_keyboard())


@router.message(AdminStates.waiting_moment_title)
async def add_memorable_moment_title_step(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    if not message.text:
        await message.answer("Надішліть назву текстом.")
        return
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return

    await state.update_data(moment_title=message.text.strip())
    await state.set_state(AdminStates.waiting_moment_description)
    await message.answer(
        "Додайте опис або оберіть 'Без опису'.",
        reply_markup=moment_description_keyboard(),
    )


@router.message(AdminStates.waiting_moment_description)
async def add_memorable_moment_description_step(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    if not message.text:
        await message.answer("Надішліть опис текстом або натисніть 'Без опису'.")
        return
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return

    description = None if message.text == BTN_SKIP_DESCRIPTION else message.text.strip()
    await state.update_data(moment_description=description)
    await state.set_state(AdminStates.waiting_moment_media)
    await message.answer(
        "Надішліть фото або відео для памʼятного моменту, або оберіть 'Без фото/відео'.",
        reply_markup=moment_media_keyboard(),
    )


@router.message(AdminStates.waiting_moment_media)
async def add_memorable_moment_media_step(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return

    data = await state.get_data()
    media_type = data.get("moment_media_type")
    media_file_ids = list(data.get("moment_media_file_ids", []))

    if message.text == BTN_SKIP_MEDIA:
        await state.update_data(moment_media_type=None, moment_media_file_ids=[])
    elif message.text == BTN_MEDIA_DONE:
        if not media_file_ids:
            await message.answer("Ви ще не додали медіа. Надішліть фото/відео або натисніть 'Без фото/відео'.")
            return
    elif message.photo:
        if media_type == "video":
            await message.answer("Не можна змішувати фото і відео. Надішліть ✅ Готово або Скасувати.")
            return
        media_type = "photo"
        media_file_ids.append(message.photo[-1].file_id)
        await state.update_data(moment_media_type=media_type, moment_media_file_ids=media_file_ids)
        await message.answer(
            f"Додано фото: {len(media_file_ids)}. Можете надіслати ще або натиснути 'Готово'.",
            reply_markup=moment_media_keyboard(),
        )
        return
    elif message.video:
        if media_type == "photo" and media_file_ids:
            await message.answer("Не можна змішувати фото і відео. Надішліть ✅ Готово або Скасувати.")
            return
        media_type = "video"
        media_file_ids = [message.video.file_id]
        await state.update_data(moment_media_type=media_type, moment_media_file_ids=media_file_ids)
    else:
        await message.answer("Очікую фото, відео або кнопку 'Без фото/відео'.")
        return

    await state.set_state(AdminStates.waiting_moment_date)
    await message.answer(
        "Вкажіть дату у форматі YYYY-MM-DD або DD.MM.YYYY, або натисніть 'Сьогодні'.",
        reply_markup=moment_date_keyboard(),
    )


@router.message(AdminStates.waiting_moment_date)
async def add_memorable_moment_date_step(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    if not message.text:
        await message.answer("Надішліть дату текстом.")
        return
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return

    moment_date = date.today() if message.text == BTN_TODAY else parse_moment_date(message.text)
    if moment_date is None:
        await message.answer("Невірний формат дати. Приклад: 2026-03-03 або 03.03.2026")
        return

    await state.update_data(moment_date=moment_date.isoformat())
    await state.set_state(AdminStates.waiting_moment_hashtags)
    await message.answer(
        "Додайте хештеги (наприклад: #firstStep #family) або оберіть 'Автохештеги'.",
        reply_markup=moment_hashtag_keyboard(),
    )


@router.message(AdminStates.waiting_moment_hashtags)
async def add_memorable_moment_hashtags_step(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    if not message.text or not message.from_user:
        return
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return

    data = await state.get_data()
    title = str(data.get("moment_title", "")).strip()
    if not title:
        await state.clear()
        await message.answer("Не знайдено назву. Запустіть сценарій ще раз.", reply_markup=admin_keyboard())
        return

    description = data.get("moment_description")
    moment_date_str = str(data.get("moment_date"))
    moment_date = parse_moment_date(moment_date_str) if moment_date_str else None
    if moment_date is None:
        moment_date = date.today()

    media_type = data.get("moment_media_type")
    media_file_ids = list(data.get("moment_media_file_ids", []))

    manual_hashtags = [] if message.text == BTN_AUTO_HASHTAGS else extract_hashtags(message.text)
    hashtag_text = ensure_hashtags(" ".join(manual_hashtags), extra=["#MemorableMoment"])

    async with SessionLocal() as session:
        moment_service = MemorableMomentService(session)
        moment = await moment_service.create_moment(
            title=title,
            description=description,
            moment_date=moment_date,
            created_by=message.from_user.id,
            hashtags=hashtag_text,
            media_type=media_type,
            media_file_id=media_file_ids[0] if media_file_ids else None,
        )

    sent = await broadcast_memorable_moment(
        bot=message.bot,
        title=title,
        description=description,
        moment_date=moment_date,
        hashtags_text=hashtag_text,
        media_type=media_type,
        media_file_ids=media_file_ids,
        moment_id=moment.id,
    )

    await state.clear()
    await message.answer(
        "✅ Памʼятний момент додано.\n"
        f"ID: <code>{moment.id}</code>\n"
        f"Розіслано: {sent} користувачам",
        reply_markup=admin_keyboard(),
    )


@router.message(F.text == BTN_GROWTH)
async def growth_entry(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    await state.clear()
    await message.answer(
        "Оберіть, що хочете зафіксувати у календарі розвитку:",
        reply_markup=growth_keyboard(),
    )


@router.message(F.text.in_({BTN_GROWTH_WEIGHT, BTN_GROWTH_HEIGHT}))
async def growth_value_entry(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message) or not message.text:
        return
    mode = "weight" if message.text == BTN_GROWTH_WEIGHT else "height"
    await state.set_state(AdminStates.waiting_growth_value)
    await state.update_data(growth_mode=mode)
    hint = "у грамах (наприклад 5300)" if mode == "weight" else "у сантиметрах (наприклад 62.5)"
    await message.answer(f"Введіть значення {hint}.", reply_markup=cancel_keyboard())


@router.message(AdminStates.waiting_growth_value)
async def growth_value_submit(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message) or not message.text or not message.from_user:
        return
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return

    data = await state.get_data()
    mode = data.get("growth_mode")
    if mode not in {"weight", "height"}:
        await state.clear()
        await message.answer("Не знайдено тип вимірювання. Спробуйте ще раз.", reply_markup=admin_keyboard())
        return

    try:
        value = float(message.text.replace(",", ".").strip())
    except ValueError:
        await message.answer("Невірний формат числа. Спробуйте ще раз.")
        return
    if value <= 0:
        await message.answer("Значення має бути більше 0.")
        return

    async with SessionLocal() as session:
        growth = GrowthService(session)
        record = await growth.create_record(
            record_type=mode,
            value=value,
            created_by=message.from_user.id,
        )
        prev = await growth.previous_record_before(mode, record.id)

    await state.clear()

    if mode == "weight":
        if prev and prev.value:
            diff = int(round(value - prev.value))
            sign = "+" if diff >= 0 else ""
            channel_text = (
                f"🍼 Свіже оновлення розвитку Аліси!\n"
                f"Вага зараз: {int(value)} г\n"
                f"Зміна від попереднього виміру: {sign}{diff} г 💛"
            )
        else:
            channel_text = f"🍼 Свіже оновлення розвитку Аліси!\nПоточна вага: {int(value)} г 💛"
        admin_text = f"✅ Вагу збережено: {int(value)} г"
    else:
        if prev and prev.value:
            diff = value - prev.value
            sign = "+" if diff >= 0 else ""
            channel_text = (
                f"📏 Новина з календаря розвитку!\n"
                f"Зріст Аліси: {value:.1f} см\n"
                f"Приріст: {sign}{diff:.1f} см 🌱"
            )
        else:
            channel_text = f"📏 Новина з календаря розвитку!\nПоточний зріст Аліси: {value:.1f} см 🌱"
        admin_text = f"✅ Зріст збережено: {value:.1f} см"

    try:
        await message.bot.send_message(settings.channel_id, channel_text)
    except Exception:
        pass

    await message.answer(admin_text, reply_markup=admin_keyboard())


@router.message(F.text == BTN_GROWTH_EVENT)
async def growth_event_entry(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    await state.set_state(AdminStates.waiting_growth_event_title)
    await message.answer(
        "Введіть назву події (наприклад: Перший зуб, Перші кроки, Місяць №3 виконано 🎉).",
        reply_markup=cancel_keyboard(),
    )


@router.message(AdminStates.waiting_growth_event_title)
async def growth_event_title_submit(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message) or not message.text:
        return
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return
    await state.update_data(growth_event_title=message.text.strip())
    await state.set_state(AdminStates.waiting_growth_event_note)
    await message.answer("Додайте короткий коментар до події (або '-' якщо без коментаря).")


@router.message(AdminStates.waiting_growth_event_note)
async def growth_event_note_submit(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message) or not message.text or not message.from_user:
        return
    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return
    data = await state.get_data()
    title = str(data.get("growth_event_title", "")).strip()
    if not title:
        await state.clear()
        await message.answer("Не знайдено назву події. Спробуйте ще раз.", reply_markup=admin_keyboard())
        return
    note = None if message.text.strip() == "-" else message.text.strip()
    async with SessionLocal() as session:
        growth = GrowthService(session)
        await growth.create_record(
            record_type="event",
            title=title,
            note=note,
            created_by=message.from_user.id,
        )
    await state.clear()
    channel_text = f"👣 Новий памʼятний запис у календарі розвитку: {title}\n{note or ''}".strip()
    try:
        await message.bot.send_message(settings.channel_id, channel_text)
    except Exception:
        pass
    await message.answer("✅ Подію збережено і опубліковано в канал.", reply_markup=admin_keyboard())


@router.message(F.text == BTN_NEW_POST)
async def new_post_entry(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    await state.set_state(AdminStates.waiting_post_photo)
    await state.update_data(post_media_type=None, post_file_ids=[])
    await message.answer(
        "Надішліть одне або кілька фото (або одне відео). Коли завершите, натисніть 'Готово'.",
        reply_markup=post_media_keyboard(),
    )


@router.message(AdminStates.waiting_post_photo)
async def new_post_photo_step(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return

    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return

    data = await state.get_data()
    media_type = data.get("post_media_type")
    file_ids = list(data.get("post_file_ids", []))

    if message.text == BTN_MEDIA_DONE:
        if not file_ids:
            await message.answer("Спочатку додайте фото/відео, потім натискайте 'Готово'.")
            return
        await state.set_state(AdminStates.waiting_post_caption)
        await message.answer("Додайте опис до фото або оберіть 'Без опису'.", reply_markup=caption_keyboard())
        return

    if message.photo:
        if media_type == "video":
            await message.answer("Не можна змішувати фото і відео. Надішліть ✅ Готово або Скасувати.")
            return
        media_type = "photo"
        file_ids.append(message.photo[-1].file_id)
        await state.update_data(post_media_type=media_type, post_file_ids=file_ids)
        await message.answer(
            f"Додано фото: {len(file_ids)}. Можете надіслати ще або натиснути 'Готово'.",
            reply_markup=post_media_keyboard(),
        )
        return

    if message.video:
        if media_type == "photo" and file_ids:
            await message.answer("Не можна змішувати фото і відео. Надішліть ✅ Готово або Скасувати.")
            return
        media_type = "video"
        file_ids = [message.video.file_id]
        await state.update_data(post_media_type=media_type, post_file_ids=file_ids)
        await state.set_state(AdminStates.waiting_post_caption)
        await message.answer("Відео додано. Додайте опис або оберіть 'Без опису'.", reply_markup=caption_keyboard())
        return

    await message.answer("Очікую фото/відео або кнопку 'Готово'.")


@router.message(AdminStates.waiting_post_caption)
async def new_post_caption_step(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    if not message.text:
        await message.answer("Надішліть текст опису або натисніть 'Без опису'.")
        return

    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return

    raw_caption = None if message.text == BTN_SKIP_CAPTION else message.text.strip()
    caption = ensure_hashtags(raw_caption)
    await state.update_data(caption=caption)
    await state.set_state(AdminStates.waiting_post_schedule_choice)
    await message.answer("Коли публікувати пост?", reply_markup=publish_choice_keyboard())


@router.callback_query(F.data == "post:now")
async def publish_now_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_super_admin_callback(callback):
        return

    current_state = await state.get_state()
    if current_state != AdminStates.waiting_post_schedule_choice.state:
        await callback.answer("Немає активного сценарію публікації", show_alert=True)
        return

    data = await state.get_data()
    media_type = data.get("post_media_type") or "photo"
    file_ids = list(data.get("post_file_ids", []))
    caption = data.get("caption")
    if not file_ids:
        await callback.answer("Не знайдено медіа", show_alert=True)
        return

    await publish_media(
        bot=callback.bot,
        chat_id=settings.channel_id,
        media_type=media_type,
        file_ids=file_ids,
        caption=ensure_hashtags(caption),
    )
    await state.clear()

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Пост опубліковано в канал.", reply_markup=admin_keyboard())
    await callback.answer()


@router.callback_query(F.data == "post:later")
async def publish_later_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_super_admin_callback(callback):
        return

    current_state = await state.get_state()
    if current_state != AdminStates.waiting_post_schedule_choice.state:
        await callback.answer("Немає активного сценарію публікації", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_post_datetime)
    if callback.message:
        sample_local = (datetime.now(KYIV_TZ) + timedelta(minutes=10)).replace(second=0, microsecond=0)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "Вкажіть дату і час публікації.\n"
            "Формати:\n"
            "<code>2026-03-03 22:30</code>\n"
            "<code>03.03.2026 22:30</code>\n"
            f"Наприклад на сьогодні: <code>{sample_local.strftime('%Y-%m-%d %H:%M')}</code>\n"
            "Часовий пояс: Europe/Kyiv",
            reply_markup=cancel_keyboard(),
        )
    await callback.answer()


@router.message(AdminStates.waiting_post_datetime)
async def post_datetime_step(message: Message, state: FSMContext) -> None:
    if not is_super_admin_message(message):
        return
    if not message.text:
        await message.answer("Надішліть дату і час текстом.")
        return

    if message.text == BTN_CANCEL:
        await state.clear()
        await message.answer("Дію скасовано.", reply_markup=admin_keyboard())
        return

    publish_at_local = parse_publish_datetime(message.text)
    if not publish_at_local:
        await message.answer(
            "Невірний формат.\n"
            "Спробуйте: <code>2026-03-03 22:30</code> або <code>03.03.2026 22:30</code>"
        )
        return

    if publish_at_local <= datetime.now(KYIV_TZ):
        await message.answer("Цей час вже минув. Вкажіть майбутню дату.")
        return

    data = await state.get_data()
    media_type = data.get("post_media_type") or "photo"
    file_ids = list(data.get("post_file_ids", []))
    caption = data.get("caption")
    if not file_ids or not message.from_user:
        await message.answer("Не знайдено фото для публікації. Запустіть сценарій ще раз.")
        await state.clear()
        return

    publish_at_utc = publish_at_local.astimezone(timezone.utc)

    async with SessionLocal() as session:
        service = ScheduledPostService(session)
        post = await service.create_scheduled_post(
            file_id=encode_scheduled_media_ref(media_type=media_type, file_ids=file_ids),
            caption=ensure_hashtags(caption),
            publish_at=publish_at_utc,
            created_by_telegram_id=message.from_user.id,
        )

    await state.clear()
    await message.answer(
        "✅ Публікацію заплановано\n"
        f"ID: <code>{post.id}</code>\n"
        f"Коли: {publish_at_local.strftime('%d.%m.%Y %H:%M')} (Europe/Kyiv)",
        reply_markup=admin_keyboard(),
    )


@router.message(F.text == BTN_STATS)
async def stats_handler(message: Message) -> None:
    if not is_super_admin_message(message):
        return

    async with SessionLocal() as session:
        service = UserService(session)
        stats = await service.get_stats()
        moments_count = await session.scalar(select(func.count()).select_from(MemorableMoment))
        total_donations = await session.scalar(select(func.coalesce(func.sum(Donation.amount), 0)).select_from(Donation))

    await message.answer(
        "Статистика:\n"
        f"Усього користувачів: {stats.total_users}\n"
        f"Активних: {stats.active_users}\n"
        f"Очікують підтвердження: {stats.pending_users}\n"
        f"Памʼятних моментів: {moments_count or 0}\n"
        f"Донати: {int(total_donations or 0)} UAH",
        reply_markup=admin_keyboard(),
    )
