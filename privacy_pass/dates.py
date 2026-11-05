"""Shift every calendar date in a document by one shared day offset.

Intervals stay. Absolute calendar alignment with real records breaks.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

# Same format catalogue as the protect-list date parser, longest first.
_DATE_FORMATS = (
    "%B %d, %Y",
    "%B %d %Y",
    "%b %d, %Y",
    "%b. %d, %Y",
    "%b %d %Y",
    "%d %B %Y",
    "%d %B, %Y",
    "%d %b %Y",
    "%d %b, %Y",
    "%d %b. %Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%Y%m%d",
)

# Rough finder: enough to locate candidates; strptime confirms.
_DATE_FINDER = re.compile(
    r"""
    (?<!\w)
    (?:
        (?:January|February|March|April|May|June|July|August|September|October|November|December|
           Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)
        \s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}
      | \d{1,2}\s+
        (?:January|February|March|April|May|June|July|August|September|October|November|December|
           Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)
        ,?\s+\d{4}
      | \d{4}-\d{2}-\d{2}
      | \d{4}/\d{2}/\d{2}
      | \d{1,2}/\d{1,2}/\d{2,4}
      | \d{1,2}-\d{1,2}-\d{4}
      | \d{8}
    )
    (?!\w)
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class DateShift:
    original: str
    shifted: str
    start: int
    end: int
    value: date


@dataclass
class DateShiftResult:
    text: str
    offset_days: int
    shifts: list[DateShift]


def choose_offset(rng: random.Random | None = None) -> int:
    """Non-zero offset so a real calendar never matches by accident."""
    rng = rng or random.Random()
    offset = 0
    while offset == 0:
        offset = rng.randint(-120, 120)
    return offset


def shift_dates(
    text: str,
    offset_days: int | None = None,
    rng: random.Random | None = None,
) -> DateShiftResult:
    """Rewrite every recognized calendar date by the same day offset."""
    offset = choose_offset(rng) if offset_days is None else offset_days
    if offset == 0:
        return DateShiftResult(text=text, offset_days=0, shifts=[])

    hits: list[tuple[int, int, date, str, str]] = []
    for match in _DATE_FINDER.finditer(text):
        parsed = _parse_date(match.group())
        if not parsed:
            continue
        value, fmt = parsed
        hits.append((match.start(), match.end(), value, match.group(), fmt))

    # Longest / leftmost first to avoid nested double-hits.
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    accepted: list[tuple[int, int, date, str, str]] = []
    for hit in hits:
        if any(hit[0] < a[1] and a[0] < hit[1] for a in accepted):
            continue
        accepted.append(hit)
    accepted.sort(key=lambda h: h[0])

    pieces: list[str] = []
    shifts: list[DateShift] = []
    cursor = 0
    for start, end, value, original, fmt in accepted:
        shifted_value = value + timedelta(days=offset)
        shifted = _format_like(shifted_value, fmt, original)
        pieces.append(text[cursor:start])
        pieces.append(shifted)
        shifts.append(
            DateShift(
                original=original,
                shifted=shifted,
                start=start,
                end=end,
                value=value,
            )
        )
        cursor = end
    pieces.append(text[cursor:])
    return DateShiftResult(text="".join(pieces), offset_days=offset, shifts=shifts)


def unshift_dates(text: str, shifts: list[DateShift] | list[dict]) -> str:
    """Restore original dates from the shifted forms present in `text`."""
    pairs: list[tuple[str, str]] = []
    for item in shifts:
        if isinstance(item, DateShift):
            pairs.append((item.shifted, item.original))
        else:
            pairs.append((item["shifted"], item["original"]))
    # Longest shifted string first so nested substrings don't collide.
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    out = text
    for shifted, original in pairs:
        out = re.sub(re.escape(shifted), original, out, flags=re.IGNORECASE)
    return out


def _parse_date(raw: str) -> tuple[date, str] | None:
    stripped = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", raw.strip(), flags=re.IGNORECASE)
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(stripped, fmt).replace(tzinfo=UTC).date()
        except ValueError:
            continue
        if parsed.year > datetime.now(UTC).year + 1:
            parsed = parsed.replace(year=parsed.year - 100)
        if parsed.year < 1800:
            continue
        return parsed, fmt
    return None


def _format_like(value: date, fmt: str, original: str) -> str:
    """Emit the shifted date in the same format family as the original."""
    if "%B" in fmt:
        day = value.day
        if ", %Y" in fmt and fmt.startswith("%B"):
            return f"{value.strftime('%B')} {day}, {value.year}"
        if fmt.startswith("%d"):
            return f"{day} {value.strftime('%B')} {value.year}"
        return f"{value.strftime('%B')} {day} {value.year}"
    if "%b" in fmt:
        day = value.day
        short = value.strftime("%b")
        if original.lstrip()[3:4] == "." or ". " in original[:6]:
            short = short + "."
        if fmt.startswith("%d"):
            return f"{day} {short} {value.year}"
        if "," in fmt:
            return f"{short} {day}, {value.year}"
        return f"{short} {day} {value.year}"
    if fmt == "%Y-%m-%d":
        return value.isoformat()
    if fmt == "%Y/%m/%d":
        return value.strftime("%Y/%m/%d")
    if fmt == "%m/%d/%Y":
        return f"{value.month}/{value.day}/{value.year}"
    if fmt == "%m-%d-%Y":
        return f"{value.month:02d}-{value.day:02d}-{value.year}"
    if fmt == "%m/%d/%y":
        return f"{value.month}/{value.day}/{value.strftime('%y')}"
    if fmt == "%Y%m%d":
        return value.strftime("%Y%m%d")
    return value.strftime(fmt)
