from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from app.crm.services.parser import parse_auto_ria, ParseError, CarInfo
from app.crm.services import lead_service
from app.crm.handlers.work_card import show_work_card
from app.crm.states import AddLeadStates
from app.crm.utils.helpers import is_primary_super_admin
from app.crm.constants import STATUS_LABELS
import re

router = Router()

URL_PATTERN = re.compile(r"https?://auto.ria.com/uk/auto_[\w_]+_\d+\.html")
OLX_PATTERN = re.compile(r"https?://www\.olx\.ua/.+?/obyavlenie/.+")

def _format_preview(car_info: CarInfo) -> str:
    phone_text = f"📞 {car_info.phone}" if car_info.phone else "📞 <i>Номер скрыт — добавите вручную</i>"
    price_text = f"${car_info.price}" if car_info.currency == "USD" else f"{car_info.price} {car_info.currency}"
    mileage_text = f"{car_info.mileage / 1000 if car_info.mileage else 'N/A'} тыс. км"
    location_text = car_info.location or "—"
    seller_text = car_info.seller_name or "—"
    desc = car_info.description[:150] + "..." if car_info.description else ""
    return (
        f"🚗 <b>{car_info.brand} {car_info.model}</b> {car_info.year or ''}\n"
        f"💰 <b>{price_text}</b>\n"
        f"📍 {location_text}\n"
        f"📏 {mileage_text}\n\n"
        f"👤 <b>{seller_text}</b>\n"
        f"{phone_text}\n\n"
        f"<i>{desc}</i>"
    )


@router.message(F.text & F.text.contains("auto.ria.com"))
async def process_url(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    match = URL_PATTERN.search(message.text)
    if not match:
        await message.answer("❌ Невірне посилання Auto.ria. Спробуйте інше.")
        return

    url = match.group(0)
    await message.answer("🔍 Парсю дані з Auto.ria...")

    try:
        car_info = await parse_auto_ria(url)
        lead, created = await lead_service.create_lead(car_info, url, message.from_user.id)
        if not created:
            status_label = STATUS_LABELS.get(lead.status, lead.status)
            await message.answer(f"⚠️ Это авто уже в базе (статус: {status_label}).")
        else:
            await message.answer("✅ Авто додано в базу на прозвон.")

    except ParseError:
        car_info = CarInfo(
            source="auto_ria",
            brand="AutoRia",
            model="Ссылка",
            year=None,
            price=0,
            currency="USD",
            mileage=None,
            location=None,
            vin=None,
            photos=[],
            description=None,
            phone=None,
            seller_name=None,
            phone_hidden=True,
        )
        lead, created = await lead_service.create_lead(car_info, url, message.from_user.id)
        if not created:
            status_label = STATUS_LABELS.get(lead.status, lead.status)
            await message.answer(f"⚠️ Это авто уже в базе (статус: {status_label}).")
        else:
            await message.answer("⚠️ Не вдалося зчитати сторінку автоматично.\n✅ Посилання додано. Заповніть дані в картці вручну.")
    finally:
        await state.clear()


@router.message(F.text & F.text.contains("olx.ua"))
async def process_olx_url(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    match = OLX_PATTERN.search(message.text or "")
    if not match:
        await message.answer("❌ Невірне посилання OLX. Спробуйте інше.")
        return

    url = match.group(0)
    await message.answer("🔗 Зберігаю посилання OLX...")

    try:
        car_info = CarInfo(
            source="olx",
            brand="OLX",
            model="Ссылка",
            year=None,
            price=0,
            currency="USD",
            mileage=None,
            location=None,
            vin=None,
            photos=[],
            description=None,
            phone=None,
            seller_name=None,
            phone_hidden=True,
        )
        lead, created = await lead_service.create_lead(car_info, url, message.from_user.id)
        if not created:
            status_label = STATUS_LABELS.get(lead.status, lead.status)
            await message.answer(f"⚠️ Это авто уже в базе (статус: {status_label}).")
        else:
            await message.answer("✅ Посилання додано. Заповніть дані в картці вручну.")
    except ParseError as e:
        await message.answer(f"❌ Помилка: {e}")
    finally:
        await state.clear()

@router.callback_query(F.data == "cancel_lead_add", AddLeadStates.confirm_data)
async def cancel_add(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("❌ Отменено.")
    await state.clear()
