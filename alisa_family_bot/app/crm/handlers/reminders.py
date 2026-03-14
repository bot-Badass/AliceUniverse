from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime

from app.crm.keyboards.common import get_reminder_keyboard, get_reminder_actions_keyboard
from app.crm.keyboards.main import get_main_crm_keyboard
from app.crm.states import ReminderStates
from app.crm.services import reminder_service
from app.crm.services import lead_service
from app.crm.utils.helpers import is_primary_super_admin, parse_human_datetime, to_utc, KYIV_TZ
from app.crm.handlers.work_card import show_work_card

router = Router()


@router.message(F.text == "⏰ Напоминания")
async def show_reminders(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    items = await reminder_service.list_upcoming_reminders(message.from_user.id, limit=10)
    if not items:
        await message.answer("Напоминаний нет.", reply_markup=get_main_crm_keyboard())
        return
    await message.answer("⏰ Ближайшие напоминания:", reply_markup=get_main_crm_keyboard())
    for r in items:
        lead = await reminder_service.get_lead(r.lead_id)
        dt = r.remind_at.astimezone(KYIV_TZ)
        car_text = f"{lead.car_brand} {lead.car_model} {lead.car_year}" if lead else "—"
        owner_text = lead.owner_name or "—" if lead else "—"
        text = (
            f"• {dt.strftime('%d.%m %H:%M')} — {r.message}\n"
            f"👤 {owner_text}\n"
            f"🚗 {car_text}"
        )
        await message.answer(text, reply_markup=get_reminder_keyboard(r.id))


@router.callback_query(F.data.startswith("reminder:actions:"))
async def reminder_actions(callback_query: types.CallbackQuery):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    reminder_id = int(callback_query.data.split(":")[-1])
    await callback_query.message.edit_reply_markup(reply_markup=get_reminder_actions_keyboard(reminder_id))
    await callback_query.answer()


@router.callback_query(F.data.startswith("reminder:done:"))
async def reminder_done(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    reminder_id = int(callback_query.data.split(":")[-1])
    reminder = await reminder_service.get_reminder(reminder_id)
    if not reminder:
        await callback_query.answer("Напоминание не найдено", show_alert=True)
        return
    await reminder_service.mark_reminder_completed(reminder_id)
    lead = await reminder_service.get_lead(reminder.lead_id)
    if lead:
        await callback_query.message.edit_reply_markup(reply_markup=None)
        await show_work_card(callback_query.message, state, lead)
    await callback_query.answer()


@router.callback_query(F.data.startswith("reminder:for_sale:"))
async def reminder_for_sale(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    reminder_id = int(callback_query.data.split(":")[-1])
    reminder = await reminder_service.get_reminder(reminder_id)
    if not reminder:
        await callback_query.answer("Напоминание не найдено", show_alert=True)
        return
    lead = await reminder_service.get_lead(reminder.lead_id)
    if not lead:
        await callback_query.answer("Лид не найден", show_alert=True)
        return
    await lead_service.update_status(lead.id, "for_sale_set")
    await lead_service.add_call_log(
        lead_id=lead.id,
        manager_id=callback_query.from_user.id,
        result="for_sale_set",
        notes="Из напоминания",
    )
    await reminder_service.mark_reminder_completed(reminder_id)
    await callback_query.message.edit_reply_markup(reply_markup=None)
    await callback_query.message.answer("✅ Авто поставлено в продажу.")
    await show_work_card(callback_query.message, state, lead)
    await callback_query.answer()


@router.callback_query(F.data.startswith("reminder:open:"))
async def reminder_open(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    reminder_id = int(callback_query.data.split(":")[-1])
    reminder = await reminder_service.get_reminder(reminder_id)
    if not reminder:
        await callback_query.answer("Напоминание не найдено", show_alert=True)
        return
    lead = await reminder_service.get_lead(reminder.lead_id)
    if not lead:
        await callback_query.answer("Лид не найден", show_alert=True)
        return
    await show_work_card(callback_query.message, state, lead)
    await callback_query.answer()


@router.callback_query(F.data.startswith("reminder:cancel:"))
async def reminder_cancel(callback_query: types.CallbackQuery):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    reminder_id = int(callback_query.data.split(":")[-1])
    await reminder_service.mark_reminder_completed(reminder_id)
    await callback_query.message.edit_reply_markup(reply_markup=None)
    await callback_query.answer("Напоминание отменено")


@router.callback_query(F.data.startswith("reminder:reschedule:"))
async def reminder_reschedule(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    reminder_id = int(callback_query.data.split(":")[-1])
    await state.set_state(ReminderStates.waiting_datetime)
    await state.update_data(reminder_id=reminder_id)
    await callback_query.message.edit_reply_markup(reply_markup=None)
    await callback_query.message.answer(
        "Укажи новое время. Примеры: \"завтра 15:00\", \"15.03 11:00\", \"пн 10:30\", \"сегодня вечером\"."
    )
    await callback_query.answer()


@router.message(ReminderStates.waiting_datetime)
async def reminder_reschedule_input(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    if not message.text:
        await message.answer("Нужно текстом указать дату и время.")
        return
    data = await state.get_data()
    reminder_id = data.get("reminder_id")
    dt_local = parse_human_datetime(message.text)
    if not dt_local:
        await message.answer("Не смог разобрать дату. Примеры: \"завтра 15:00\", \"15.03 11:00\".")
        return
    await reminder_service.update_reminder_time(int(reminder_id), to_utc(dt_local))
    await state.clear()
    await message.answer(f"Перенесено на {dt_local.strftime('%d.%m %H:%M')}.", reply_markup=get_main_crm_keyboard())


async def send_reminder(bot, reminder) -> None:
    lead = await reminder_service.get_lead(reminder.lead_id)
    if not lead:
        return
    dt_local = reminder.remind_at.astimezone(KYIV_TZ)
    text = (
        "<b>🔔 НАПОМИНАНИЕ</b>\n\n"
        f"Клиент: {lead.owner_name or '—'}\n"
        f"🚗 {lead.car_brand} {lead.car_model} {lead.car_year}\n"
        f"💰 ${lead.car_price}\n\n"
        f"⏰ Было назначено: {dt_local.strftime('%d.%m %H:%M')}\n"
        f"📝 Ваши заметки: \"{reminder.message}\""
    )
    await bot.send_message(reminder.manager_id, text, reply_markup=get_reminder_keyboard(reminder.id))
