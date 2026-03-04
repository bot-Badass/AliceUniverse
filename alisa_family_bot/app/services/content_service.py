from __future__ import annotations

import re

DEFAULT_HASHTAGS = ["#AliceUniverse", "#AlisaFamily"]
HASHTAG_RE = re.compile(r"#[\w\d_]+", flags=re.UNICODE)


def extract_hashtags(text: str | None) -> list[str]:
    if not text:
        return []
    found = HASHTAG_RE.findall(text)
    seen: set[str] = set()
    unique: list[str] = []
    for tag in found:
        lowered = tag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(tag)
    return unique


def ensure_hashtags(text: str | None, extra: list[str] | None = None) -> str:
    base = (text or "").strip()
    existing = extract_hashtags(base)

    normalized_existing = {tag.lower() for tag in existing}
    required = list(DEFAULT_HASHTAGS)
    if extra:
        required.extend(extra)

    to_add = [tag for tag in required if tag.lower() not in normalized_existing]

    if not base and not to_add:
        return ""
    if not base:
        return " ".join(to_add)
    if not to_add:
        return base
    return f"{base}\n\n{' '.join(to_add)}"
