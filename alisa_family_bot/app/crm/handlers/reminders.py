from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from app.crm.constants import CALLBACK_PREFIXES
from app.crm.keyboards.reminders import get_reminders_keyboard
from app.crm.services.lead_service import get_lead_by_id
from app.crm.services.reminder_service import get_user_reminders
from app.crm.models import Reminder

router = Router()

@router.message(F.text == "⏰ Напоминания")
async def reminders_menu(message: Message, state: FSMContext):
    # Main reminders menu handler
    await state.clear()
    await message.answer(
        "🔔 <b>Напоминания</b>\n\n"
        "Выберите действие:",
        reply_markup=get_reminders_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "crm_reminders:list")
async def reminders_list(callback: CallbackQuery, state: FSMContext):
    # Show user's reminders list
    manager_id = callback.from_user.id
    reminders = await get_user_reminders(manager_id)
    
    if not reminders:
        text = "📭 У вас нет активных напоминаний\n\nНапоминания создаются при работе с карточками авто."
        try:
            await callback.message.edit_text(text, reply_markup=get_reminders_keyboard(), parse_mode="HTML")
        except:
            await callback.message.answer(text, reply_markup=get_reminders_keyboard(), parse_mode="HTML")
        await callback.answer()
        return
    
    text = "🔔 <b>Ваши напоминания</b>\n\n"
    for r in reminders[:10]:  # limit 10
        dt = r.remind_at.strftime("%d.%m %H:%M")
        text += f"⏰ {dt} | {r.message}\n"
    
    # Build keyboard
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить", callback_data="crm_reminders:list")
    kb.button(text="⬅️ Меню", callback_data="crm_reminders:menu")
    kb.adjust(2)
    
    try:
        await callback.message.edit_text(
            text + "\n<i>Активные напоминания (не завершенные)</i>",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    except:
        await callback.message.answer(
            text + "\n<i>Активные напоминания (не завершенные)</i>",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data == "crm_reminders:menu")
async def reminders_back_menu(callback: CallbackQuery, state: FSMContext):
    # Back to reminders menu
    await callback.message.edit_text(
        "🔔 <b>Напоминания</b>\n\n"
        "Выберите действие:",
        reply_markup=get_reminders_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

async def send_reminder(bot: Bot, reminder: Reminder) -> None:
    # Send reminder to manager (used by scheduler)
    lead = await get_lead_by_id(reminder.lead_id)
    if not lead:
        return

    text = (
        f"🔔 <b>НАПОМИНАНИЕ</b>\n\n"
        f"Тип: {reminder.reminder_type}\n"
        f"Сообщение: {reminder.message}\n\n"
        f"🚗 {lead.car_brand} {lead.car_model} ({lead.car_year or '?' })\n"
        f"💰 ${lead.car_price}\n"
        f"📞 {lead.owner_phone or 'Номер не указан'}"
    )

    try:
        await bot.send_message(chat_id=reminder.manager_id, text=text, parse_mode="HTML")
    except Exception:
        # Manager might have blocked bot
        pass

