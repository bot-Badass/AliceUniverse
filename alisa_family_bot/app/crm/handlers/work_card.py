from aiogram import Router, F, types
import re
from aiogram.types import InputMediaPhoto
from aiogram.fsm.context import FSMContext
from app.crm.models import Lead
from app.crm.keyboards.card import get_work_card_keyboard, get_card_edit_keyboard, get_call_result_keyboard
from app.crm.keyboards.main import get_main_crm_keyboard
from app.crm.services import lead_service
from app.crm.services import reminder_service
from app.crm.states import WorkCardStates
from app.crm.utils.helpers import is_primary_super_admin, parse_human_datetime, to_utc, KYIV_TZ
from app.crm.constants import STATUS_LABELS

router = Router()

MENU_COMMANDS = {
    "/crm",
    "📋 Очередь на звонок",
    "⏰ Напоминания",
    "🏷 База в продаже",
    "📊 CRM Стат",
    "📊 Статистика CRM",
}

async def _advance_to_next_card(message: types.Message, state: FSMContext) -> bool:
    data = await state.get_data()
    list_ids = data.get("list_ids") or []
    list_index = data.get("list_index")
    list_type = data.get("list_type")
    if list_ids and list_index is not None:
        next_index = (list_index + 1) % len(list_ids)
        lead = await lead_service.get_lead_by_id(list_ids[next_index])
        if lead:
            await show_work_card(
                message,
                state,
                lead,
                list_ids=list_ids,
                list_index=next_index,
                list_type=list_type,
                replace=True,
            )
            return True
    next_lead = await lead_service.get_first_lead_from_pipeline()
    if not next_lead:
        await message.answer("Очередь пуста.", reply_markup=get_main_crm_keyboard())
        return True
    await show_work_card(message, state, next_lead, replace=True)
    return True

def _build_tel_url(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    if digits.startswith("380") and len(digits) in {11, 12}:
        return f"tel:+{digits}"
    if digits.startswith("0") and len(digits) == 10:
        return f"tel:+38{digits}"
    if digits.startswith("8") and len(digits) == 11:
        return f"tel:+3{digits}"
    if len(digits) >= 11 and phone.strip().startswith("+"):
        return f"tel:+{digits}"
    return None

def _allowed_statuses(current: str) -> list[str]:
    if current in {"new", "thinking", "callback_scheduled", "no_answer"}:
        return [
            "callback_scheduled",
            "appointment_set",
            "rejected",
            "no_answer",
        ]
    if current == "appointment_set":
        return [
            "for_sale_set",
            "rejected",
        ]
    if current == "for_sale_set":
        return [
            "published",
            "returned",
        ]
    if current == "published":
        return [
            "sold",
            "returned",
        ]
    return []

def _is_sale_status(status: str) -> bool:
    return status in {"for_sale_set", "published", "sold", "returned"}

def _split_text(text: str, limit: int = 4000) -> list[str]:
    chunks = []
    buf = text
    while buf:
        chunks.append(buf[:limit])
        buf = buf[limit:]
    return chunks

async def show_work_card(
    message: types.Message,
    state: FSMContext,
    lead: Lead,
    list_ids: list[int] | None = None,
    list_index: int | None = None,
    list_type: str | None = None,
    replace: bool = False,
):
    await state.set_state(WorkCardStates.in_call)
    await state.update_data(lead_id=lead.id, lead_status=lead.status)
    if list_ids is not None and list_index is not None and list_type:
        await state.update_data(list_ids=list_ids, list_index=list_index, list_type=list_type)
        with_nav = True
    else:
        await state.update_data(list_ids=None, list_index=None, list_type=None)
        with_nav = False

    # Format from README 6.4
    logs = await lead_service.list_call_logs(lead.id, limit=5)
    history_lines = []
    for log in logs:
        ts = log.created_at.strftime('%Y-%m-%d %H:%M')
        label = STATUS_LABELS.get(log.result, log.result)
        note = None
        if log.notes and log.notes.startswith("voice:"):
            note = "🎤 Голосовая заметка"
        elif log.notes:
            note = log.notes
        if log.next_action_date:
            next_ts = log.next_action_date.strftime('%Y-%m-%d %H:%M')
            history_lines.append(f"• {ts} — {label} → {next_ts} {note or ''}".strip())
        elif note:
            history_lines.append(f"• {ts} — {label} — {note}")
        else:
            history_lines.append(f"• {ts} — {label}")
    history_text = "\n".join(history_lines) if history_lines else f"• {lead.created_at.strftime('%Y-%m-%d %H:%M')} — Добавлен в систему"

    status_label = STATUS_LABELS.get(lead.status, lead.status)
    price_text = f"${lead.car_price}" if lead.car_price_currency == "USD" else f"{lead.car_price} {lead.car_price_currency}"
    phone_url = None
    has_details = bool(lead.car_description or lead.car_photos)
    text = (
        f"🚗 <b>{lead.car_brand} {lead.car_model}</b> {lead.car_year}\n"
        f"💰 {price_text} • 📍 {lead.car_location} • 📏 {lead.car_mileage / 1000 if lead.car_mileage else 'N/A'} тыс. км\n"
        f"Статус: {status_label}\n\n"
        f"👤 {lead.owner_name}\n"
        f"📞 {lead.owner_phone or 'Номер не указан'}\n"
        f"🔗 {lead.source_url or '—'}\n"
        f"📝 История:\n"
        f"{history_text}\n"
        f"\nПодсказка: \"Я позвонил\" фиксирует результат и добавляет запись в историю."
    )

    keyboard = get_work_card_keyboard(
        with_nav=with_nav,
        phone_url=phone_url,
        has_details=has_details,
    )
    if replace:
        try:
            await message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return
        except Exception:
            pass
    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "card:next_queue")
async def card_next_queue(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    next_lead = await lead_service.get_first_lead_from_pipeline()
    if not next_lead:
        await callback_query.message.answer("Очередь пуста.", reply_markup=get_main_crm_keyboard())
        await callback_query.answer()
        return
    await show_work_card(callback_query.message, state, next_lead, replace=True)
    await callback_query.answer()


@router.callback_query(F.data == "card:next")
async def card_browse_next(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    data = await state.get_data()
    list_ids = data.get("list_ids") or []
    list_index = data.get("list_index")
    list_type = data.get("list_type")
    if list_index is None or not list_ids:
        await callback_query.answer("Нет списка для просмотра", show_alert=True)
        return
    next_index = (list_index + 1) % len(list_ids)
    lead = await lead_service.get_lead_by_id(list_ids[next_index])
    if not lead:
        await callback_query.answer("Лид не найден", show_alert=True)
        return
    await show_work_card(callback_query.message, state, lead, list_ids=list_ids, list_index=next_index, list_type=list_type, replace=True)
    await callback_query.answer()


@router.callback_query(F.data == "card:prev")
async def card_browse_prev(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    data = await state.get_data()
    list_ids = data.get("list_ids") or []
    list_index = data.get("list_index")
    list_type = data.get("list_type")
    if list_index is None or not list_ids:
        await callback_query.answer("Нет списка для просмотра", show_alert=True)
        return
    prev_index = (list_index - 1) % len(list_ids)
    lead = await lead_service.get_lead_by_id(list_ids[prev_index])
    if not lead:
        await callback_query.answer("Лид не найден", show_alert=True)
        return
    await show_work_card(callback_query.message, state, lead, list_ids=list_ids, list_index=prev_index, list_type=list_type, replace=True)
    await callback_query.answer()


@router.callback_query(F.data == "card:menu")
async def card_menu(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    await state.clear()
    await callback_query.message.answer("CRM Module Main Menu", reply_markup=get_main_crm_keyboard())
    await callback_query.answer()


@router.callback_query(F.data == "card:details")
async def card_details(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    data = await state.get_data()
    lead_id = data.get("lead_id")
    if not lead_id:
        await callback_query.answer("Карточка не активна", show_alert=True)
        return
    lead = await lead_service.get_lead_by_id(int(lead_id))
    if not lead:
        await callback_query.answer("Лид не найден", show_alert=True)
        return
    if lead.car_photos:
        media = []
        for idx, url in enumerate(lead.car_photos[:10]):
            media.append(InputMediaPhoto(media=url))
        await callback_query.message.answer_media_group(media)
        if lead.car_description:
            for chunk in _split_text(lead.car_description, limit=4000):
                await callback_query.message.answer(chunk)
    elif lead.car_description:
        for chunk in _split_text(lead.car_description, limit=4000):
            await callback_query.message.answer(chunk)
    else:
        await callback_query.message.answer("Подробностей нет.")
    await callback_query.answer()


@router.callback_query(F.data == "card:add_note")
async def card_add_note(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    await state.set_state(WorkCardStates.adding_notes)
    await callback_query.message.answer("Добавь заметку текстом или голосовым.")
    await callback_query.answer()


@router.callback_query(F.data == "card:call")
async def card_call(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    await state.set_state(WorkCardStates.waiting_result)
    await callback_query.message.edit_reply_markup(reply_markup=get_call_result_keyboard())
    await callback_query.answer()


@router.callback_query(F.data == "card:edit")
async def card_edit(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    await state.set_state(WorkCardStates.edit_field)
    await callback_query.message.answer("Что редактируем?", reply_markup=get_card_edit_keyboard())
    await callback_query.answer()


@router.callback_query(F.data.startswith("cardedit:"), WorkCardStates.edit_field)
async def card_edit_choose(callback_query: types.CallbackQuery, state: FSMContext):
    field = callback_query.data.split(":")[-1]
    if field == "back":
        await state.set_state(WorkCardStates.in_call)
        await callback_query.answer()
        return
    await state.set_state(WorkCardStates.edit_value)
    await state.update_data(edit_field=field)
    await callback_query.message.answer("Введи новое значение.")
    await callback_query.answer()


@router.message(WorkCardStates.edit_value)
async def card_edit_value(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    data = await state.get_data()
    field = data.get("edit_field")
    lead_id = data.get("lead_id")
    if not field or not lead_id:
        await message.answer("Карточка не активна.")
        return
    if not message.text:
        await message.answer("Нужно значение текстом.")
        return
    value = message.text.strip()
    fields = {}
    if field == "year" and value.isdigit():
        fields["car_year"] = int(value)
    elif field == "price":
        digits = "".join([c for c in value if c.isdigit()])
        if digits:
            fields["car_price"] = int(digits)
    elif field == "brand":
        fields["car_brand"] = value
    elif field == "model":
        fields["car_model"] = value
    elif field == "location":
        fields["car_location"] = value
    elif field == "owner":
        fields["owner_name"] = value
    elif field == "phone":
        fields["owner_phone"] = value
        fields["owner_phone_hidden"] = False

    if fields:
        await lead_service.update_lead_fields(int(lead_id), **fields)
        await message.answer("Данные обновлены.")
    else:
        await message.answer("Не удалось обновить поле.")
    await state.set_state(WorkCardStates.in_call)


@router.callback_query(F.data.startswith("card:status:"))
async def card_set_status(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    data = await state.get_data()
    lead_id = data.get("lead_id")
    if not lead_id:
        await callback_query.answer("Карточка не активна", show_alert=True)
        return
    lead = await lead_service.get_lead_by_id(int(lead_id))
    if not lead:
        await callback_query.answer("Лид не найден", show_alert=True)
        return
    status = callback_query.data.split(":")[-1]
    if status not in _allowed_statuses(lead.status):
        await callback_query.answer("Этот статус сейчас недоступен", show_alert=True)
        return
    if status in {"thinking", "appointment_set", "callback_scheduled"}:
        await state.set_state(WorkCardStates.thinking_set_date if status == "thinking" else WorkCardStates.appointment_set_date)
        await state.update_data(pending_status=status, lead_id=int(lead_id))
        await callback_query.message.answer(
            "Когда перезвонить? Примеры: \"завтра 15:00\", \"15.03 11:00\", \"пн 10:30\", \"сегодня вечером\"."
        )
        await callback_query.answer()
        return

    updated = await lead_service.update_status(int(lead_id), status)
    if not updated:
        await callback_query.answer("⚠️ Ошибка: нельзя перевести в этот статус", show_alert=True)
        return
    await lead_service.add_call_log(
        lead_id=int(lead_id),
        manager_id=callback_query.from_user.id,
        result=status,
        notes=None,
    )
    label = STATUS_LABELS.get(status, status)
    await callback_query.message.answer(f"Статус обновлен: {label}")
    data = await state.get_data()
    list_ids = data.get("list_ids") or []
    list_index = data.get("list_index")
    list_type = data.get("list_type")
    if list_ids and list_index is not None:
        next_index = min(list_index + 1, len(list_ids) - 1)
        lead = await lead_service.get_lead_by_id(list_ids[next_index])
        if lead:
            await show_work_card(
                callback_query.message,
                state,
                lead,
                list_ids=list_ids,
                list_index=next_index,
                list_type=list_type,
                replace=True,
            )
            await callback_query.answer()
            return
    next_lead = await lead_service.get_first_lead_from_pipeline()
    if not next_lead:
        await callback_query.message.answer("Очередь пуста.", reply_markup=get_main_crm_keyboard())
        await callback_query.answer()
        return
    await show_work_card(callback_query.message, state, next_lead, replace=True)
    await callback_query.answer()


@router.message(WorkCardStates.thinking_set_date)
async def set_thinking_date(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    data = await state.get_data()
    lead_id = data.get("lead_id")
    if not message.text or not lead_id:
        await message.answer("Нужно указать дату и время текстом.")
        return
    dt_local = parse_human_datetime(message.text)
    if not dt_local:
        await message.answer("Не смог разобрать дату. Примеры: \"завтра 15:00\", \"15.03 11:00\".")
        return
    await reminder_service.create_reminder(
        lead_id=int(lead_id),
        manager_id=message.from_user.id,
        remind_at=to_utc(dt_local),
        reminder_type="callback",
        message="Перезвонить клиенту",
    )
    await lead_service.update_status(int(lead_id), "thinking")
    await lead_service.add_call_log(
        lead_id=int(lead_id),
        manager_id=message.from_user.id,
        result="thinking",
        notes=None,
        next_action_type="callback",
        next_action_date=to_utc(dt_local),
    )
    await message.answer(f"✅ Напоминание установлено: {dt_local.strftime('%d.%m %H:%M')}")
    await _advance_to_next_card(message, state)


@router.message(WorkCardStates.adding_notes)
async def add_note(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    data = await state.get_data()
    lead_id = data.get("lead_id")
    if not lead_id:
        await message.answer("Карточка не активна.")
        return
    note_text = None
    if message.text:
        note_text = message.text.strip()
    elif message.voice:
        note_text = f"voice:{message.voice.file_id}"
    if not note_text:
        await message.answer("Нужна текстовая или голосовая заметка.")
        return
    await lead_service.add_call_log(
        lead_id=int(lead_id),
        manager_id=message.from_user.id,
        result="note",
        notes=note_text,
    )
    await state.set_state(WorkCardStates.in_call)
    await message.answer("Заметка сохранена.")


@router.message(WorkCardStates.waiting_result, F.text, ~F.text.in_(MENU_COMMANDS))
async def call_result_input(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    await message.answer("Використай кнопки нижче для вибору результату дзвінка.")


@router.callback_query(F.data.startswith("callres:"))
async def call_result_button(callback_query: types.CallbackQuery, state: FSMContext):
    if not is_primary_super_admin(callback_query.from_user.id if callback_query.from_user else None):
        return
    await callback_query.message.edit_reply_markup(reply_markup=None)
    data = await state.get_data()
    lead_id = data.get("lead_id")
    if not lead_id:
        await callback_query.answer("Карточка не активна", show_alert=True)
        return
    lead = await lead_service.get_lead_by_id(int(lead_id))
    if not lead:
        await callback_query.answer("Лид не найден", show_alert=True)
        return
    status = callback_query.data.split(":")[-1]
    if status not in _allowed_statuses(lead.status):
        await callback_query.answer("Этот статус сейчас недоступен", show_alert=True)
        return

    if status in {"thinking", "appointment_set", "callback_scheduled"}:
        await state.set_state(WorkCardStates.thinking_set_date if status == "thinking" else WorkCardStates.appointment_set_date)
        await state.update_data(pending_status=status, lead_id=int(lead_id))
        await callback_query.message.answer(
            "Коли передзвонити? Приклади: \"завтра 15:00\", \"15.03 11:00\", \"пн 10:30\", \"сьогодні ввечері\"."
        )
        await callback_query.answer()
        return

    await lead_service.update_status(int(lead_id), status)
    await lead_service.add_call_log(
        lead_id=int(lead_id),
        manager_id=callback_query.from_user.id,
        result=status,
        notes=None,
    )
    await state.set_state(WorkCardStates.in_call)
    label = STATUS_LABELS.get(status, status)
    await callback_query.message.answer(f"Статус оновлено: {label}")

    data = await state.get_data()
    list_ids = data.get("list_ids") or []
    list_index = data.get("list_index")
    list_type = data.get("list_type")
    if list_ids and list_index is not None:
        next_index = min(list_index + 1, len(list_ids) - 1)
        next_lead = await lead_service.get_lead_by_id(list_ids[next_index])
        if next_lead:
            await show_work_card(
                callback_query.message,
                state,
                next_lead,
                list_ids=list_ids,
                list_index=next_index,
                list_type=list_type,
                replace=True,
            )
            await callback_query.answer()
            return
    next_lead = await lead_service.get_first_lead_from_pipeline()
    if not next_lead:
        await callback_query.message.answer("Очередь пуста.", reply_markup=get_main_crm_keyboard())
        await callback_query.answer()
        return
    await show_work_card(callback_query.message, state, next_lead, replace=True)
    await callback_query.answer()


@router.message(WorkCardStates.appointment_set_date)
async def set_appointment_date(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    data = await state.get_data()
    lead_id = data.get("lead_id")
    if not message.text or not lead_id:
        await message.answer("Нужно указать дату и время текстом.")
        return
    dt_local = parse_human_datetime(message.text)
    if not dt_local:
        await message.answer("Не смог разобрать дату. Примеры: \"завтра 15:00\", \"15.03 11:00\".")
        return
    pending_status = data.get("pending_status") or "appointment_set"
    reminder_type = "appointment" if pending_status == "appointment_set" else "callback"
    reminder_message = "Встреча с клиентом" if pending_status == "appointment_set" else "Перезвонить клиенту"
    await reminder_service.create_reminder(
        lead_id=int(lead_id),
        manager_id=message.from_user.id,
        remind_at=to_utc(dt_local),
        reminder_type=reminder_type,
        message=reminder_message,
    )
    await lead_service.update_status(int(lead_id), pending_status)
    await lead_service.add_call_log(
        lead_id=int(lead_id),
        manager_id=message.from_user.id,
        result=pending_status,
        notes=None,
        next_action_type=reminder_type,
        next_action_date=to_utc(dt_local),
    )
    await message.answer(f"✅ Напоминание установлено: {dt_local.strftime('%d.%m %H:%M')}")
    await _advance_to_next_card(message, state)
