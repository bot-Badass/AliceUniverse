from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.db import SessionLocal
from app.services.engagement_service import EngagementService, month_start_utc

router = Router()

REACTION_MAP = {
    "heart": "❤️",
    "like": "👍",
    "clap": "👏",
}


class DonationStates(StatesGroup):
    waiting_amount = State()


@router.message(F.text == "👤 Мій профіль")
async def profile_handler(message: Message) -> None:
    if not message.from_user:
        return
    async with SessionLocal() as session:
        service = EngagementService(session)
        user, badges = await service.get_profile_data(message.from_user.id)

    if not user or not user.is_active:
        await message.answer("Профіль доступний після підтвердження підписки 💛")
        return

    badges_text = "\n".join([f"• {b.badge_type} — {b.description or ''}".strip() for b in badges[:10]]) or "Поки без бейджів"
    await message.answer(
        "👤 Ваш профіль\n"
        f"Ім'я: {user.full_name}\n"
        f"Роль: {user.role or '-'}\n"
        f"Задоначено всього: {user.total_donated} UAH\n"
        f"Поточний бейдж: {user.badge or '-'}\n\n"
        f"Ваші бейджі:\n{badges_text}"
    )


@router.message(F.text == "🏆 Рейтинг донаторів")
async def donor_rating_handler(message: Message) -> None:
    async with SessionLocal() as session:
        service = EngagementService(session)
        month_start = month_start_utc(datetime.now(timezone.utc))
        top = await service.recalculate_monthly_top_donators(month_start)

        lines: list[str] = ["💛 Рейтинг донаторів місяця 💛", ""]
        labels = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(top):
            user = await service.get_user(row.user_id)
            name = user.full_name if user else str(row.user_id)
            lines.append(f"{labels[i]} {name}")
        if not top:
            lines.append("Поки що донатів у цьому місяці немає.")
        lines.append("")
        lines.append("Суми не публікуються, тільки місця 🤗")
    await message.answer("\n".join(lines))


@router.callback_query(F.data == "donate:report")
async def donation_report_entry(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DonationStates.waiting_amount)
    await callback.answer()
    if callback.message:
        await callback.message.answer("Вкажіть суму донату числом у UAH (наприклад: 200).")


@router.message(DonationStates.waiting_amount)
async def donation_amount_handler(message: Message, state: FSMContext) -> None:
    if not message.from_user or not message.text:
        return

    raw = message.text.strip()
    if not raw.isdigit():
        await message.answer("Невірний формат. Надішліть суму числом, наприклад: 200")
        return

    amount = int(raw)
    if amount <= 0:
        await message.answer("Сума має бути більшою за 0.")
        return

    async with SessionLocal() as session:
        service = EngagementService(session)
        user = await service.ensure_active_user(message.from_user.id)
        if not user:
            await state.clear()
            await message.answer("Дякуємо! Донати доступні лише для підтверджених учасників.")
            return

        donation = await service.add_donation(user_id=message.from_user.id, amount=amount, currency="UAH")
        refreshed = await service.ensure_active_user(message.from_user.id)

    await state.clear()
    badge_line = f"\nВаш бейдж: {refreshed.badge}" if refreshed and refreshed.badge else ""
    if donation:
        await message.answer(
            f"Дякуємо за підтримку Аліси 💛\n"
            f"Сума: {donation.amount} {donation.currency}\n"
            f"Загалом задоначено: {refreshed.total_donated if refreshed else amount} UAH"
            f"{badge_line}"
        )


@router.callback_query(F.data.startswith("react:"))
async def reaction_handler(callback: CallbackQuery) -> None:
    if not callback.data or not callback.from_user:
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Невірний формат", show_alert=True)
        return

    _, object_type, object_id_raw, reaction_key = parts
    reaction_emoji = REACTION_MAP.get(reaction_key)
    if reaction_emoji is None:
        await callback.answer("Невідома реакція", show_alert=True)
        return

    try:
        object_id = int(object_id_raw)
    except ValueError:
        await callback.answer("Невірний ID", show_alert=True)
        return

    if object_type not in {"photo", "moment"}:
        await callback.answer("Невірний тип", show_alert=True)
        return

    async with SessionLocal() as session:
        service = EngagementService(session)
        user = await service.ensure_active_user(callback.from_user.id)
        if not user:
            await callback.answer("Лише для підтверджених учасників", show_alert=True)
            return

        await service.add_or_update_reaction(
            user_id=callback.from_user.id,
            object_type=object_type,
            object_id=object_id,
            reaction=reaction_emoji,
        )

        if object_type == "moment":
            await service.add_or_update_moment_reaction(
                moment_id=object_id,
                user_id=callback.from_user.id,
                reaction=reaction_emoji,
            )

        updated = await service.update_badge(callback.from_user.id)

    badge_suffix = f" | {updated.badge}" if updated and updated.badge else ""
    await callback.answer(f"Реакцію збережено: {reaction_emoji}{badge_suffix}")
