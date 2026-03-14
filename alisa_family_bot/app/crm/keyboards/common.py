from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_reminder_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="⚙️ Действия", callback_data=f"reminder:actions:{reminder_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_reminder_actions_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📋 Показати картку", callback_data=f"reminder:open:{reminder_id}")],
        [InlineKeyboardButton(text="✅ Я позвонил", callback_data=f"reminder:done:{reminder_id}")],
        [InlineKeyboardButton(text="📝 Встала в продажу", callback_data=f"reminder:for_sale:{reminder_id}")],
        [InlineKeyboardButton(text="⏰ Перенести", callback_data=f"reminder:reschedule:{reminder_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"reminder:cancel:{reminder_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
