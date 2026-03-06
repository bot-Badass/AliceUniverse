from __future__ import annotations

import asyncio
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import get_settings
from app.db import SessionLocal
from app.services.morning_service import MorningService

router = Router()
settings = get_settings()

MORNING_STEPS = [
    {"key": "no_phone", "title": "📵 Не проверять телефон 7 минут", "timer": 7 * 60},
    {"key": "light", "title": "🌤 Выйти на свет в первые 15 минут", "timer": 5 * 60},
    {"key": "water", "title": "💧 Выпить 300–500 мл воды", "timer": None},
    {"key": "meditation", "title": "🧘 Медитация 10–12 минут", "timer": 10 * 60},
    {"key": "movement", "title": "🏃 Легкое движение 5–10 минут", "timer": None},
    {"key": "gratitude", "title": "🙏 3 благодарности", "timer": None},
    {"key": "priority", "title": "🎯 1 главный приоритет дня", "timer": None},
    {"key": "breakfast", "title": "🍳 Полезный завтрак", "timer": None},
    {"key": "deep_task", "title": "🧠 Сложная задача в первые 2 часа", "timer": None},
]

MOVEMENT_MODES = {
    "A": {
        "title": "A) Mobility Flow (6 минут)",
        "duration": 6 * 60,
        "short": "Мягкая мобильность и дыхание.",
        "details": (
            "1) Круги шеи и плеч (60 сек): стойка ровная, медленные круги головой и плечами без рывков.\n"
            "2) Повороты грудного отдела (60 сек): стойка в выпаде, рука вверх, вращение грудной клетки, таз стабилен.\n"
            "3) Глубокий присед удержание (60 сек): пятки на полу, локтями мягко раскрывать колени.\n"
            "4) Hip hinge без веса (60 сек): таз назад, спина нейтральная, возврат за счет ягодиц.\n"
            "5) Голеностоп + икры (60 сек): колено к стене с пяткой на полу, затем медленные подъемы на носки.\n"
            "6) Дыхание 4-6 (60 сек): вдох 4 счета, выдох 6 счетов."
        ),
    },
    "B": {
        "title": "B) Activation Flow (8 минут)",
        "duration": 8 * 60,
        "short": "Активация без жимовых движений.",
        "details": (
            "2 круга по 40 сек работа / 20 сек отдых:\n"
            "1) Приседания: таз назад-вниз, колени по линии носков, подъем через пятки.\n"
            "2) Обратные выпады: шаг назад, корпус ровный, колено не заваливается внутрь.\n"
            "3) Ягодичный мост: подъем таза до прямой линии плечи-таз-колени, без переразгиба поясницы.\n"
            "4) Dead bug: поясница прижата, поочередно вытягивать противоположные руку и ногу."
        ),
    },
    "C": {
        "title": "C) Athletic Primer (10 минут)",
        "duration": 10 * 60,
        "short": "Более интенсивно, без жимов.",
        "details": (
            "3 круга, отдых 45 сек между кругами:\n"
            "1) Jumping jacks 30 сек: мягкое приземление, колени мягкие.\n"
            "2) Air squats 12: контроль коленей, пятки на полу.\n"
            "3) Reverse lunges 10/нога: корпус стабилен, шаг назад.\n"
            "4) Standing knee drives 20: поочередно подтягивать колени к груди.\n"
            "5) High knees 30 сек: бег на месте с высоким подъемом колен."
        ),
    },
}

MEDITATION_DETAILS = (
    "Сядьте удобно, спина ровная, плечи расслаблены.\n"
    "Закройте глаза или смотрите в одну точку.\n"
    "Дыхание носом: вдох 4 счета, выдох 6 счетов.\n"
    "Если отвлеклись — спокойно верните внимание к дыханию.\n"
    "Задача не выключить мысли, а тренировать возврат фокуса."
)

TIMER_TASKS: dict[int, asyncio.Task] = {}


class MorningStates(StatesGroup):
    waiting_gratitude = State()
    waiting_priority = State()


def is_primary_super_admin(user_id: int) -> bool:
    return settings.primary_super_admin is not None and user_id == settings.primary_super_admin


async def ensure_primary_message_access(message: Message) -> bool:
    if not message.from_user:
        return False
    return is_primary_super_admin(message.from_user.id)


async def ensure_primary_callback_access(callback: CallbackQuery) -> bool:
    if not callback.from_user:
        return False
    return is_primary_super_admin(callback.from_user.id)


def step_by_index(index: int) -> dict[str, Any] | None:
    if index < 0 or index >= len(MORNING_STEPS):
        return None
    return MORNING_STEPS[index]


def morning_step_keyboard(step_key: str, with_timer: bool = False, with_details: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton(text="✅ Выполнил", callback_data="morning:done")])
    if with_timer:
        rows.append([InlineKeyboardButton(text="⏱ Запустить таймер", callback_data="morning:timer")])
    if step_key in {"gratitude", "priority"}:
        rows.append([InlineKeyboardButton(text="✍️ Ввести ответ", callback_data="morning:input")])
    if step_key == "movement":
        rows.append(
            [
                InlineKeyboardButton(text="A Mobility", callback_data="morning:mode:A"),
                InlineKeyboardButton(text="B Activation", callback_data="morning:mode:B"),
                InlineKeyboardButton(text="C Athletic", callback_data="morning:mode:C"),
            ]
        )
    if with_details:
        rows.append([InlineKeyboardButton(text="📘 Показать технику подробно", callback_data="morning:details")])
    rows.append(
        [
            InlineKeyboardButton(text="⏭ Пропустить", callback_data="morning:skip"),
            InlineKeyboardButton(text="🛑 Завершить", callback_data="morning:stop"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_timer_for_user(user_id: int) -> None:
    task = TIMER_TASKS.pop(user_id, None)
    if task and not task.done():
        task.cancel()


async def schedule_timer(bot, user_id: int, chat_id: int, step_key: str, seconds: int) -> None:
    cancel_timer_for_user(user_id)

    async def _timer() -> None:
        await asyncio.sleep(seconds)
        step = next((s for s in MORNING_STEPS if s["key"] == step_key), None)
        if not step:
            return
        with_details = step_key in {"movement", "meditation"}
        keyboard = morning_step_keyboard(step_key, with_timer=False, with_details=with_details)
        await bot.send_message(
            chat_id,
            f"⏰ Таймер для шага завершен: {step['title']}\nГотово отметить выполнение?",
            reply_markup=keyboard,
        )

    TIMER_TASKS[user_id] = asyncio.create_task(_timer())


async def send_step_prompt(target: Message | CallbackQuery, state: FSMContext, user_id: int, chat_id: int) -> None:
    data = await state.get_data()
    step_index = int(data.get("step_index", 0))
    session_id = int(data.get("session_id"))

    step = step_by_index(step_index)
    if step is None:
        async with SessionLocal() as session:
            service = MorningService(session)
            finished = await service.finish_session(session_id=session_id, status="done")
            streak = await service.get_streak(user_id)

        cancel_timer_for_user(user_id)
        text = "✅ Ранковий протокол завершено!"
        if finished:
            text += f"\nВиконано кроків: {finished.completed_steps}/{len(MORNING_STEPS)}"
        if streak:
            text += f"\nСерія: {streak.current_streak} дн. (рекорд: {streak.best_streak})"
        text += "\nСильний старт дня, тримай темп 💪"

        if isinstance(target, CallbackQuery):
            await target.message.answer(text)
            await target.answer()
        else:
            await target.answer(text)
        await state.clear()
        return

    async with SessionLocal() as session:
        service = MorningService(session)
        await service.start_step(session_id=session_id, step_key=step["key"])

    with_timer = bool(step.get("timer")) or step["key"] == "movement"
    with_details = step["key"] in {"movement", "meditation"}
    keyboard = morning_step_keyboard(step["key"], with_timer=with_timer, with_details=with_details)

    text = f"Крок {step_index + 1}/{len(MORNING_STEPS)}\n{step['title']}"
    if step["key"] == "movement":
        text += "\nОбери режим нижче, потім натисни «⏱ Запустить таймер»."
    if step["key"] == "gratitude":
        text += "\nНатисни «✍️ Ввести ответ» і запиши 3 вдячності."
    if step["key"] == "priority":
        text += "\nНатисни «✍️ Ввести ответ» і запиши 1 головний пріоритет дня."

    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=keyboard)
        await target.answer()
    else:
        await target.answer(text, reply_markup=keyboard)


@router.message(F.text == "🌅 Проснулся")
async def morning_start_handler(message: Message, state: FSMContext) -> None:
    if not await ensure_primary_message_access(message):
        return

    user_id = message.from_user.id
    async with SessionLocal() as session:
        service = MorningService(session)
        morning_session = await service.start_session(user_id=user_id)

    await state.clear()
    await state.update_data(session_id=morning_session.id, step_index=0, movement_mode=None)
    await message.answer(
        "Починаємо ранковий протокол ☀️\n"
        "Фокус: ясність, енергія та перший важливий результат дня.\n"
        "Рухайся крок за кроком, я проведу.",
    )
    await send_step_prompt(message, state, user_id=user_id, chat_id=message.chat.id)


@router.callback_query(F.data == "morning:done")
async def morning_done_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not await ensure_primary_callback_access(callback):
        return

    data = await state.get_data()
    if not data:
        await callback.answer("Сессия не активна", show_alert=True)
        return

    session_id = int(data["session_id"])
    step_index = int(data.get("step_index", 0))
    step = step_by_index(step_index)
    if step is None:
        await callback.answer("Сессия завершена", show_alert=True)
        return

    if step["key"] == "movement" and not data.get("movement_mode"):
        await callback.answer("Сначала выберите режим движения", show_alert=True)
        return

    if step["key"] in {"gratitude", "priority"}:
        await callback.answer("Нажмите '✍️ Ввести ответ'", show_alert=True)
        return

    async with SessionLocal() as session:
        service = MorningService(session)
        await service.complete_step(session_id=session_id, step_key=step["key"])

    if step["key"] == "deep_task":
        try:
            await schedule_timer(
                bot=callback.bot,
                user_id=callback.from_user.id,
                chat_id=callback.message.chat.id,
                step_key="deep_task",
                seconds=2 * 60 * 60,
            )
        except Exception:
            pass

    await state.update_data(step_index=step_index + 1)
    await send_step_prompt(callback, state, user_id=callback.from_user.id, chat_id=callback.message.chat.id)


@router.callback_query(F.data == "morning:skip")
async def morning_skip_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not await ensure_primary_callback_access(callback):
        return

    data = await state.get_data()
    if not data:
        await callback.answer("Сессия не активна", show_alert=True)
        return

    session_id = int(data["session_id"])
    step_index = int(data.get("step_index", 0))
    step = step_by_index(step_index)
    if step is None:
        await callback.answer("Сессия завершена", show_alert=True)
        return

    async with SessionLocal() as session:
        service = MorningService(session)
        await service.skip_step(session_id=session_id, step_key=step["key"])

    await state.update_data(step_index=step_index + 1)
    await send_step_prompt(callback, state, user_id=callback.from_user.id, chat_id=callback.message.chat.id)


@router.callback_query(F.data == "morning:stop")
async def morning_stop_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not await ensure_primary_callback_access(callback):
        return

    data = await state.get_data()
    if data.get("session_id"):
        async with SessionLocal() as session:
            service = MorningService(session)
            await service.finish_session(int(data["session_id"]), status="aborted")

    cancel_timer_for_user(callback.from_user.id)
    await state.clear()
    await callback.answer("Протокол завершен")
    if callback.message:
        await callback.message.answer("🛑 Утренний протокол остановлен.")


@router.callback_query(F.data == "morning:timer")
async def morning_timer_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not await ensure_primary_callback_access(callback):
        return

    data = await state.get_data()
    if not data:
        await callback.answer("Сессия не активна", show_alert=True)
        return

    step_index = int(data.get("step_index", 0))
    step = step_by_index(step_index)
    if not step:
        await callback.answer("Сессия завершена", show_alert=True)
        return

    seconds = step.get("timer") or 0
    if step["key"] == "movement":
        mode = data.get("movement_mode")
        if not mode or mode not in MOVEMENT_MODES:
            await callback.answer("Сначала выберите режим движения", show_alert=True)
            return
        seconds = MOVEMENT_MODES[mode]["duration"]

    if seconds <= 0:
        await callback.answer("Для этого шага таймер не нужен", show_alert=True)
        return

    await schedule_timer(
        bot=callback.bot,
        user_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
        step_key=step["key"],
        seconds=int(seconds),
    )
    await callback.answer("Таймер запущено")


@router.callback_query(F.data == "morning:details")
async def morning_details_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not await ensure_primary_callback_access(callback):
        return

    data = await state.get_data()
    step_index = int(data.get("step_index", 0))
    step = step_by_index(step_index)
    if not step:
        await callback.answer("Сессия не активна", show_alert=True)
        return

    if step["key"] == "meditation":
        await callback.message.answer("📘 Техника медитации:\n" + MEDITATION_DETAILS)
        await callback.answer()
        return

    if step["key"] == "movement":
        mode = data.get("movement_mode")
        if not mode or mode not in MOVEMENT_MODES:
            await callback.answer("Сначала выберите режим движения", show_alert=True)
            return
        details = MOVEMENT_MODES[mode]["details"]
        await callback.message.answer(f"📘 Техника ({MOVEMENT_MODES[mode]['title']}):\n{details}")
        await callback.answer()
        return

    await callback.answer("Подробная техника для этого шага не требуется", show_alert=True)


@router.callback_query(F.data.startswith("morning:mode:"))
async def morning_mode_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not await ensure_primary_callback_access(callback):
        return

    mode = callback.data.split(":")[-1]
    if mode not in MOVEMENT_MODES:
        await callback.answer("Неверный режим", show_alert=True)
        return

    await state.update_data(movement_mode=mode)
    text = (
        f"Обрано режим: {MOVEMENT_MODES[mode]['title']}\n"
        f"{MOVEMENT_MODES[mode]['short']}\n"
        f"Тривалість таймера: {MOVEMENT_MODES[mode]['duration'] // 60} хв\n"
        "Далі натисни «⏱ Запустить таймер»."
    )
    await callback.message.answer(text)
    await callback.answer("Режим збережено")


@router.callback_query(F.data == "morning:input")
async def morning_input_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not await ensure_primary_callback_access(callback):
        return

    data = await state.get_data()
    step_index = int(data.get("step_index", 0))
    step = step_by_index(step_index)
    if not step:
        await callback.answer("Сессия не активна", show_alert=True)
        return

    if step["key"] == "gratitude":
        await state.set_state(MorningStates.waiting_gratitude)
        await callback.message.answer(
            "Напиши 3 вдячності одним повідомленням.\n"
            "Приклад:\n"
            "1) Добре спав\n"
            "2) Здорова родина\n"
            "3) Є енергія на важливу задачу"
        )
        await callback.answer()
        return

    if step["key"] == "priority":
        await state.set_state(MorningStates.waiting_priority)
        await callback.message.answer(
            "Напиши 1 головний пріоритет дня одним повідомленням.\n"
            "Приклад: «До 12:00 завершити презентацію для клієнта»."
        )
        await callback.answer()
        return

    await callback.answer("Для этого шага ввод не нужен", show_alert=True)


@router.message(MorningStates.waiting_gratitude)
async def morning_gratitude_submit(message: Message, state: FSMContext) -> None:
    if not await ensure_primary_message_access(message):
        return
    if not message.text:
        await message.answer("Нужен текстовый ответ.")
        return

    data = await state.get_data()
    session_id = int(data["session_id"])
    step_index = int(data.get("step_index", 0))
    step = step_by_index(step_index)
    if not step or step["key"] != "gratitude":
        await message.answer("Сейчас не шаг благодарностей.")
        return

    async with SessionLocal() as session:
        service = MorningService(session)
        await service.complete_step(session_id=session_id, step_key="gratitude", payload=message.text.strip())

    await state.set_state(None)
    await state.update_data(step_index=step_index + 1)
    await send_step_prompt(message, state, user_id=message.from_user.id, chat_id=message.chat.id)


@router.message(MorningStates.waiting_priority)
async def morning_priority_submit(message: Message, state: FSMContext) -> None:
    if not await ensure_primary_message_access(message):
        return
    if not message.text:
        await message.answer("Нужен текстовый ответ.")
        return

    data = await state.get_data()
    session_id = int(data["session_id"])
    step_index = int(data.get("step_index", 0))
    step = step_by_index(step_index)
    if not step or step["key"] != "priority":
        await message.answer("Сейчас не шаг приоритета.")
        return

    async with SessionLocal() as session:
        service = MorningService(session)
        await service.complete_step(session_id=session_id, step_key="priority", payload=message.text.strip())

    await state.set_state(None)
    await state.update_data(step_index=step_index + 1)
    await send_step_prompt(message, state, user_id=message.from_user.id, chat_id=message.chat.id)
