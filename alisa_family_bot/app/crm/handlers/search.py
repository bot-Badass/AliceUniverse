from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext

from app.crm.states import SearchStates
from app.crm.services import lead_service
from app.crm.utils.helpers import is_primary_super_admin
from app.crm.handlers.work_card import show_work_card

router = Router()


@router.message(F.text == "🔍 Поиск")
async def search_start(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    await state.set_state(SearchStates.waiting_query)
    await message.answer(
        "Введи запрос для поиска в базе продаж.\n"
        "Примеры: \"bmw 2022\", \"bmw 50000\", \"odessa 2021\", \"+380...\""
    )


@router.message(SearchStates.waiting_query)
async def search_query(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    if not message.text:
        await message.answer("Нужен текстовый запрос.")
        return
    if len(message.text.strip()) < 2:
        await message.answer("Запрос слишком короткий. Пример: \"bmw 2022\".")
        return
    results = await lead_service.search_sales(message.text, limit=10)
    if not results:
        await message.answer("Совпадений не найдено.")
        await state.clear()
        return
    list_ids = [lead.id for lead in results]
    text = "🔍 Результаты поиска:\n\n"
    for i, lead in enumerate(results):
        text += f"{i+1}. 🚗 {lead.car_brand} {lead.car_model} {lead.car_year} — ${lead.car_price} ({lead.car_location})\n"
    await message.answer(text)
    await show_work_card(message, state, results[0], list_ids=list_ids, list_index=0, list_type="sales")
