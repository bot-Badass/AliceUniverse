from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_sales_keyboard(page: int, has_prev: bool, has_next: bool, sort_by: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="▶️ Открыть карточки", callback_data=f"sales:open:{page}:{sort_by}")],
        [
            InlineKeyboardButton(text="Сорт A-Z", callback_data="sales:sort:brand"),
            InlineKeyboardButton(text="Сорт $", callback_data="sales:sort:price"),
            InlineKeyboardButton(text="Сорт год", callback_data="sales:sort:year"),
        ],
    ]
    nav_row: list[InlineKeyboardButton] = []
    if has_prev:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"sales:page:{page - 1}:{sort_by}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"sales:page:{page + 1}:{sort_by}"))
    if nav_row:
        rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)
