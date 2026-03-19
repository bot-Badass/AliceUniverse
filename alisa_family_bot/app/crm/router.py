from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from .handlers import add_lead, pipeline, work_card, reminders, sales, search, stats
from .keyboards.main import get_main_crm_keyboard
from .utils.helpers import is_primary_super_admin

crm_router = Router()
crm_router.include_router(add_lead.router)
crm_router.include_router(pipeline.router)
crm_router.include_router(work_card.router)
crm_router.include_router(reminders.router)
crm_router.include_router(sales.router)
crm_router.include_router(search.router)
crm_router.include_router(stats.router)

@crm_router.message(Command("crm"))
async def crm_start(message: Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await message.answer("CRM Module Main Menu", reply_markup=get_main_crm_keyboard())

