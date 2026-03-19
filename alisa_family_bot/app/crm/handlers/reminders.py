from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from app.crm.keyboards.reminders import get_reminders_keyboard
from app.crm.services.lead_service import get_lead_by_id
from app.crm.models import Reminder

router = Router()

@router.message(F.text == "⏰ Напоминания")
async def reminders_menu(message: Message, state: FSMContext):
    #\"\"\"Main reminders menu handler.\"\"\"
    await state.clear()
    await message.answer(
        "🔔 <b>Напоминания</b>\\n\\n"
        "Выберите действие:",
        reply_markup=get_reminders_keyboard(),
        parse_mode="HTML"
    )

async def send_reminder(bot: Bot, reminder: Reminder) -> None:
    #\"\"\"Send reminder to manager (used by scheduler).\"\"\"
    lead = await get_lead_by_id(reminder.lead_id)
    if not lead:
        return

    text = (
        f"🔔 <b>НАПОМИНАНИЕ</b>\\n\\n"
        f"Тип: {reminder.reminder_type}\\n"
        f"Сообщение: {reminder.message}\\n\\n"
        f"🚗 {lead.car_brand} {lead.car_model} ({lead.car_year or '?'})\\n"
        f"💰 ${lead.car_price}\\n"
        f"📞 {lead.owner_phone or 'Номер не указан'}"
    )

    try:
        await bot.send_message(chat_id=reminder.manager_id, text=text, parse_mode="HTML")
    except Exception:
        # Менеджер мог заблокировать бота
        pass

