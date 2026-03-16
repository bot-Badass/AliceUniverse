from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_card_edit_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🚗 Марка", callback_data="cardedit:brand")],
        [InlineKeyboardButton(text="🧾 Модель", callback_data="cardedit:model")],
        [InlineKeyboardButton(text="📅 Год", callback_data="cardedit:year")],
        [InlineKeyboardButton(text="💰 Цена", callback_data="cardedit:price")],
        [InlineKeyboardButton(text="📍 Город", callback_data="cardedit:location")],
        [InlineKeyboardButton(text="👤 Имя владельца", callback_data="cardedit:owner")],
        [InlineKeyboardButton(text="📞 Телефон", callback_data="cardedit:phone")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="cardedit:back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_call_result_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🤔 Думает", callback_data="callres:thinking"),
            InlineKeyboardButton(text="⏰ Перезв.", callback_data="callres:callback_scheduled"),
        ],
        [
            InlineKeyboardButton(text="📅 Встреча", callback_data="callres:appointment_set"),
            InlineKeyboardButton(text="📵 Нет ответа", callback_data="callres:no_answer"),
        ],
        [
            InlineKeyboardButton(text="❌ Отказ", callback_data="callres:rejected"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_priority_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="⭐️1", callback_data="card:priority:1"),
            InlineKeyboardButton(text="⭐️2", callback_data="card:priority:2"),
            InlineKeyboardButton(text="⭐️3", callback_data="card:priority:3"),
        ],
        [
            InlineKeyboardButton(text="⭐️4", callback_data="card:priority:4"),
            InlineKeyboardButton(text="⭐️5", callback_data="card:priority:5"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="card:priority:back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_work_card_keyboard(
    with_nav: bool = False,
    phone_url: str | None = None,
    has_details: bool = False,
    show_edit: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    if phone_url:
        rows.append([InlineKeyboardButton(text="📞 Позвонить", url=phone_url)])
    rows.append(
        [
            InlineKeyboardButton(text="☎️ Я позвонил", callback_data="card:call"),
            InlineKeyboardButton(text="📝 Добавить заметку", callback_data="card:add_note"),
        ]
    )
    if has_details:
        rows.append([InlineKeyboardButton(text="📋 Подробнее", callback_data="card:details")])
    if show_edit:
        rows.append([InlineKeyboardButton(text="✏️ Редактировать", callback_data="card:edit")])
    if with_nav:
        rows.append(
            [
                InlineKeyboardButton(text="⬅️ Предыдущая", callback_data="card:prev"),
                InlineKeyboardButton(text="➡️ Следующая", callback_data="card:next"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
