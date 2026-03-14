from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_pipeline_keyboard(page: int, has_prev: bool, has_next: bool, sort_by: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="▶️ Почати прозвон", callback_data=f"pipeline:open:{page}:{sort_by}")],
    ]
    nav_row: list[InlineKeyboardButton] = []
    if has_prev:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"pipeline:page:{page - 1}:{sort_by}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"pipeline:page:{page + 1}:{sort_by}"))
    if nav_row:
        rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_no_answer_keyboard(page: int, has_prev: bool, has_next: bool, sort_by: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="▶️ Почати прозвон", callback_data=f"noanswer:open:{page}:{sort_by}")],
    ]
    nav_row: list[InlineKeyboardButton] = []
    if has_prev:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"noanswer:page:{page - 1}:{sort_by}"))
    if has_next:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"noanswer:page:{page + 1}:{sort_by}"))
    if nav_row:
        rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)
