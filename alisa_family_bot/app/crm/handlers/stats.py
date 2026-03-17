from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext

from app.crm.services.analytics import daily_stats, weekly_stats, monthly_stats
from app.crm.utils.helpers import is_primary_super_admin

router = Router()


@router.message(F.text.in_(["📊 CRM Стат", "📊 Статистика CRM"]))
async def stats_handler(message: types.Message, state: FSMContext):
    if not is_primary_super_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    day = await daily_stats(message.from_user.id)
    week = await weekly_stats(message.from_user.id)
    month = await monthly_stats(message.from_user.id)

    def _block(title: str, stats: dict[str, int]) -> str:
        total = stats["total_calls"]
        successful = stats["successful_calls"]
        success_pct = int((successful / total) * 100) if total else 0
        conversion = int((stats["listed"] / total) * 1000) / 10 if total else 0.0

        details = [
            f"🤔 Думает: {stats['thinking']}" if stats.get('thinking') else None,
            f"📅 Встреч назначено: {stats['appointments']}" if stats.get('appointments') else None,
            f"⏰ Перезвонить: {stats['callback_scheduled']}" if stats.get('callback_scheduled') else None,
            f"🏆 Поставлено авто: {stats['listed']}" if stats.get('listed') else None,
            f"💰 Продано: {stats['sold']}" if stats.get('sold') else None,
            f"↩️ Возвращено: {stats['returned']}" if stats.get('returned') else None,
            f"📝 Заметок: {stats['note']}" if stats.get('note') else None,
            f"❌ Отказов: {stats['rejected']}" if stats.get('rejected') else None,
        ]

        details_text = "\n".join(filter(None, details))

        return (
            f"<b>{title}</b>\n"
            f"📞 Звонков: {total}\n"
            f"✅ Успешных дозвонов: {successful} ({success_pct}%)\n"
            f"{details_text}\n"
            f"Конверсия: {conversion}% ({stats['listed']}/{total})"
        )

    text = (
        "📊 Статистика\n\n"
        f"{_block('За день', day)}\n\n"
        f"{_block('За неделю', week)}\n\n"
        f"{_block('За месяц', month)}"
    )
    await message.answer(text, parse_mode="HTML")
