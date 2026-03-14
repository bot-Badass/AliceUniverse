STATUS_LABELS = {
    "note": "📝 Заметка",
    "thinking": "🤔 Думает",
    "callback_scheduled": "⏰ Перезвон назначен",
    "appointment_set": "📅 Встреча назначена",
    "for_sale_set": "📝 Встала в продажу",
    "published": "📣 Опубликована",
    "sold": "✅ Продано",
    "returned": "↩️ Вернули клиенту",
    "rejected": "❌ Отказ",
    "no_answer": "📵 Не отвечает",
    "invalid_phone": "☎️ Неверный номер",
}

CLOSED_STATUSES = {
    "sold",
    "returned",
    "rejected",
    "invalid_phone",
}


ALLOWED_STATUSES = set(STATUS_LABELS.keys())
