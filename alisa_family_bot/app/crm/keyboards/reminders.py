from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.crm.constants import CALLBACK_PREFIXES

def get_reminders_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Мои напоминания", callback_data=f"{CALLBACK_PREFIXES.crm_reminders}:list")
    builder.button(text="➕ Создать напоминание", callback_data=f"{CALLBACK_PREFIXES.crm_reminders}:create")
    builder.button(text="📊 Статистика напоминаний", callback_data=f"{CALLBACK_PREFIXES.crm_reminders}:stats")
    builder.button(text="⬅️ В главное меню", callback_data="crm:main")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()

def get_back_to_reminders_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад к напоминаниям", callback_data=f"{CALLBACK_PREFIXES.crm_reminders}:menu")
    return builder.as_markup()

