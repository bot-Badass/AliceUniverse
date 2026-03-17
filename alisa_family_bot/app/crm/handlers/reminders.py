from aiogram import Bot
from app.crm.models import Reminder
from app.crm.services.lead_service import get_lead_by_id


async def send_reminder(bot: Bot, reminder: Reminder) -> None:
    lead = await get_lead_by_id(reminder.lead_id)
    if not lead:
        return

    text = (
        f"🔔 <b>НАПОМИНАНИЕ</b>\n\n"
        f"Тип: {reminder.reminder_type}\n"
        f"Сообщение: {reminder.message}\n\n"
        f"🚗 {lead.car_brand} {lead.car_model} ({lead.car_year or '?'})\n"
        f"💰 ${lead.car_price}\n"
        f"📞 {lead.owner_phone or 'Номер не указан'}"
    )

    try:
        await bot.send_message(chat_id=reminder.manager_id, text=text, parse_mode="HTML")
    except Exception:
        # Менеджер мог заблокировать бота
        pass