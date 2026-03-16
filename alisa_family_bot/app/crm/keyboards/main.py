from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_crm_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="📋 Очередь на звонок")],
        [KeyboardButton(text="📵 Не отвечает")],
        [KeyboardButton(text="🤔 Думает")],
        [KeyboardButton(text="🏷 База в продаже")],
        [KeyboardButton(text="⏰ Напоминания"), KeyboardButton(text="📊 CRM Стат")],
        [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="⚙️ Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
