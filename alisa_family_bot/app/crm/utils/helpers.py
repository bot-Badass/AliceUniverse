from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import re

from app.config import get_settings


def is_primary_super_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    settings = get_settings()
    return settings.primary_super_admin is not None and user_id == settings.primary_super_admin


KYIV_TZ = ZoneInfo("Europe/Kyiv")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def parse_human_datetime(text: str) -> datetime | None:
    value = _normalize_text(text)
    now = datetime.now(KYIV_TZ)

    # quick keywords
    if value in {"сегодня", "сьогодні"}:
        return now.replace(second=0, microsecond=0)
    if value in {"завтра", "завтpa"}:
        return (now + timedelta(days=1)).replace(second=0, microsecond=0)

    # time-of-day keywords
    time_map = {
        "утром": time(9, 0),
        "вранці": time(9, 0),
        "днем": time(13, 0),
        "вдень": time(13, 0),
        "вечером": time(19, 0),
        "увечері": time(19, 0),
    }
    for key, tval in time_map.items():
        if key in value:
            base = now
            if "завтра" in value or "завтpa" in value:
                base = now + timedelta(days=1)
            return base.replace(hour=tval.hour, minute=tval.minute, second=0, microsecond=0)

    # weekday abbreviations
    week_map = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "нд": 6}
    wd_match = re.search(r"\b(пн|вт|ср|чт|пт|сб|нд)\b", value)
    time_match = re.search(r"(\d{1,2}):(\d{2})", value)
    if wd_match and time_match:
        target = week_map[wd_match.group(1)]
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        days_ahead = (target - now.weekday()) % 7
        if days_ahead == 0 and (hour, minute) <= (now.hour, now.minute):
            days_ahead = 7
        dt = now + timedelta(days=days_ahead)
        return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # dd.mm [hh:mm] or dd.mm.yyyy [hh:mm]
    dm_match = re.search(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?", value)
    if dm_match:
        day = int(dm_match.group(1))
        month = int(dm_match.group(2))
        year = dm_match.group(3)
        year_val = int(year) if year else now.year
        if year_val < 100:
            year_val += 2000
        hour = 10
        minute = 0
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
        try:
            dt = datetime(year_val, month, day, hour, minute, tzinfo=KYIV_TZ)
            return dt
        except ValueError:
            return None

    # hh:mm with today/tomorrow keywords
    if time_match and ("завтра" in value or "завтpa" in value):
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        dt = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt
    if time_match and ("сегодня" in value or "сьогодні" in value):
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt

    # hh:mm today
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt

    return None


def to_utc(dt_local: datetime) -> datetime:
    # Store UTC as naive datetime to match DB TIMESTAMP WITHOUT TIME ZONE
    return dt_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def parse_search_query(text: str) -> tuple[str | None, int | None]:
    """
    Returns (text_part, number_part). If number exists it's interpreted as year or price.
    Examples:
      "bmw 2022" -> ("bmw", 2022)
      "bmw 5000" -> ("bmw", 5000)
      "2020" -> (None, 2020)
    """
    value = _normalize_text(text)
    numbers = re.findall(r"\b\d{4,6}\b", value)
    number = int(numbers[0]) if numbers else None
    if number is not None:
        value = value.replace(numbers[0], "").strip()
    return (value if value else None, number)
