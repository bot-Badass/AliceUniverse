from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext

from app.crm.config import crm_config
from app.crm.keyboards.sales import get_sales_keyboard
from app.crm.services import lead_service
from app.crm.utils.helpers import is_primary_super_admin
from app.crm.handlers.work_card import show_work_card

router = Router()


async def render_sales(message: types.Message, page: int, sort_by: str) -> None:
    if sort_by not in {"brand", "price", "year"}:
        sort_by = "brand"
    leads = await lead_service.get_leads_for_sale(page=page, page_size=crm_config.PIPELINE_PAGE_SIZE, sort_by=sort_by)
    if not leads:
        await message.answer("🏷 База в продаже пуста.")
        return

    sort_label = {"brand": "марке", "price": "цене", "year": "году"}[sort_by]
    text = f"🏷 База в продаже (стр. {page + 1}, сортировка по {sort_label})\n\n"
    for i, lead in enumerate(leads):
        text += f"{i+1}. 🚗 {lead.car_brand} {lead.car_model} {lead.car_year} — ${lead.car_price} ({lead.car_location})\n"

    has_prev = page > 0
    has_next = len(leads) == crm_config.PIPELINE_PAGE_SIZE
    text += "\nПодсказка: выбери сортировку или открой карточки текущей страницы."
    await message.answer(text, reply_markup=get_sales_keyboard(page, has_prev, has_next, sort_by))


@router.message(F.text == "🏷 База в продаже")
async def show_sales(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await render_sales(message, page=0, sort_by="brand")


@router.callback_query(F.data.startswith("sales:page:"))
async def sales_page(callback_query: types.CallbackQuery):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    _, _, page, sort_by = callback_query.data.split(":")
    await render_sales(callback_query.message, page=int(page), sort_by=sort_by)
    await callback_query.answer()


@router.callback_query(F.data.startswith("sales:open:"))
async def sales_open(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    _, _, page, sort_by = callback_query.data.split(":")
    leads = await lead_service.get_leads_for_sale(page=int(page), page_size=crm_config.PIPELINE_PAGE_SIZE, sort_by=sort_by)
    if not leads:
        await callback_query.answer("База пуста", show_alert=True)
        return
    list_ids = [lead.id for lead in leads]
    await show_work_card(callback_query.message, state, leads[0], list_ids=list_ids, list_index=0, list_type="sales")
    await callback_query.answer()


@router.callback_query(F.data.startswith("sales:sort:"))
async def sales_sort(callback_query: types.CallbackQuery):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    sort_by = callback_query.data.split(":")[-1]
    await render_sales(callback_query.message, page=0, sort_by=sort_by)
    await callback_query.answer()
