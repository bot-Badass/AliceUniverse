from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.crm.constants import CALLBACK_PREFIXES

def get_reminders_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Список напоминаний", callback_data=f"{CALLBACK_PREFIXES.crm_reminders}:list")
    builder.button(text="⬅️ Главное меню", callback_data="crm:main")
    builder.adjust(1, 1)
    return builder.as_markup()

