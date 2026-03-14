from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_confirm_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ Добавить в очередь", callback_data="add_to_queue")],
        [InlineKeyboardButton(text="✏️ Редактировать данные", callback_data="edit_lead_data")],
        [InlineKeyboardButton(text="📞 Добавить номер вручную", callback_data="add_phone_manual")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_lead_add")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_duplicate_keyboard(lead_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📋 Открыть карточку", callback_data=f"dup:open:{lead_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_lead_add")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_edit_fields_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🚗 Марка", callback_data="edit:brand")],
        [InlineKeyboardButton(text="🧾 Модель", callback_data="edit:model")],
        [InlineKeyboardButton(text="📅 Год", callback_data="edit:year")],
        [InlineKeyboardButton(text="💰 Цена", callback_data="edit:price")],
        [InlineKeyboardButton(text="📍 Город", callback_data="edit:location")],
        [InlineKeyboardButton(text="👤 Имя владельца", callback_data="edit:owner")],
        [InlineKeyboardButton(text="📞 Телефон", callback_data="edit:phone")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="edit:back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
