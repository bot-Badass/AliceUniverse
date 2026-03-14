from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from app.crm.services import lead_service
from app.crm.keyboards.pipeline import get_pipeline_keyboard, get_no_answer_keyboard
from app.crm.config import crm_config
from app.crm.utils.helpers import is_primary_super_admin
from app.crm.handlers.work_card import show_work_card

router = Router()

async def render_no_answer(message: types.Message, page: int, sort_by: str) -> None:
    if sort_by not in {"brand", "price", "year"}:
        sort_by = "brand"
    leads = await lead_service.get_leads_for_no_answer(page=page, page_size=crm_config.PIPELINE_PAGE_SIZE, sort_by=sort_by)
    if not leads:
        await message.answer("📵 Нет ответов в базе.")
        return

    text = f"📵 Не отвечает (стр. {page + 1})\n\n"
    for i, lead in enumerate(leads):
        text += f"{i+1}. 🚗 {lead.car_brand} {lead.car_model} {lead.car_year} — ${lead.car_price} ({lead.car_location})\n"

    has_prev = page > 0
    has_next = len(leads) == crm_config.PIPELINE_PAGE_SIZE
    text += "\nПодсказка: начни прозвон поточной страницы."
    await message.answer(text, reply_markup=get_no_answer_keyboard(page, has_prev, has_next, sort_by))

async def render_pipeline(message: types.Message, page: int, sort_by: str) -> None:
    if sort_by not in {"brand", "price", "year"}:
        sort_by = "brand"
    leads = await lead_service.get_leads_for_pipeline(page=page, page_size=crm_config.PIPELINE_PAGE_SIZE, sort_by=sort_by)
    if not leads:
        await message.answer("📋 Очередь пуста.")
        return

    text = f"📋 Очередь на звонок (стр. {page + 1})\n\n"
    for i, lead in enumerate(leads):
        text += f"{i+1}. 🚗 {lead.car_brand} {lead.car_model} {lead.car_year} — ${lead.car_price} ({lead.car_location})\n"

    has_prev = page > 0
    has_next = len(leads) == crm_config.PIPELINE_PAGE_SIZE
    text += "\nПодсказка: начни прозвон поточной страницы."
    await message.answer(text, reply_markup=get_pipeline_keyboard(page, has_prev, has_next, sort_by))


@router.message(F.text == "📋 Очередь на звонок")
async def show_pipeline(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await render_pipeline(message, page=0, sort_by="brand")


@router.message(F.text == "📵 Не отвечает")
async def show_no_answer(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await render_no_answer(message, page=0, sort_by="brand")


@router.callback_query(F.data.startswith("pipeline:page:"))
async def pipeline_page(callback_query: types.CallbackQuery):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    _, _, page, sort_by = callback_query.data.split(":")
    await render_pipeline(callback_query.message, page=int(page), sort_by=sort_by)
    await callback_query.answer()


@router.callback_query(F.data.startswith("pipeline:open:"))
async def pipeline_open(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    _, _, page, sort_by = callback_query.data.split(":")
    leads = await lead_service.get_leads_for_pipeline(page=int(page), page_size=crm_config.PIPELINE_PAGE_SIZE, sort_by=sort_by)
    if not leads:
        await callback_query.answer("Очередь пуста", show_alert=True)
        return
    list_ids = [lead.id for lead in leads]
    await show_work_card(callback_query.message, state, leads[0], list_ids=list_ids, list_index=0, list_type="pipeline")
    await callback_query.answer()


@router.callback_query(F.data.startswith("noanswer:page:"))
async def noanswer_page(callback_query: types.CallbackQuery):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    _, _, page, sort_by = callback_query.data.split(":")
    await render_no_answer(callback_query.message, page=int(page), sort_by=sort_by)
    await callback_query.answer()


@router.callback_query(F.data.startswith("noanswer:open:"))
async def noanswer_open(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    _, _, page, sort_by = callback_query.data.split(":")
    leads = await lead_service.get_leads_for_no_answer(page=int(page), page_size=crm_config.PIPELINE_PAGE_SIZE, sort_by=sort_by)
    if not leads:
        await callback_query.answer("Нет лидов", show_alert=True)
        return
    list_ids = [l.id for l in leads]
    await show_work_card(callback_query.message, state, leads[0], list_ids=list_ids, list_index=0, list_type="no_answer")
    await callback_query.answer()


@router.callback_query(F.data.startswith("pipeline:sort:"))
async def pipeline_sort(callback_query: types.CallbackQuery):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    sort_by = callback_query.data.split(":")[-1]
    await render_pipeline(callback_query.message, page=0, sort_by=sort_by)
    await callback_query.answer()


@router.callback_query(F.data == "start_call_pipeline")
async def start_call_pipeline(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    lead = await lead_service.get_first_lead_from_pipeline(sort_by="brand")
    if not lead:
        await callback_query.answer("Очередь пуста", show_alert=True)
        return
    await show_work_card(callback_query.message, state, lead)
    await callback_query.answer()
