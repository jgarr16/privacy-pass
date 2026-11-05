"""Apply curated coarsen rules and surface leftover quasi-identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from privacy_pass.generalize import CASE_SPECIFIC_ALIASES, GENERALIZE_RULES


@dataclass(frozen=True)
class CoarsenHit:
    original: str
    replacement: str
    category: str
    start: int
    end: int


@dataclass
class CoarsenResult:
    text: str
    hits: list[CoarsenHit]


@dataclass(frozen=True)
class ReviewItem:
    kind: str  # coarsen_available | date_shifted | leftover_hint
    text: str
    detail: str
    category: str = ""
    replacement: str = ""


def apply_coarsen(
    text: str,
    *,
    include_case_specific: bool = True,
    skip_terms: list[str] | None = None,
) -> CoarsenResult:
    """Rewrite specific identifying phrases to coarser wording."""
    skipped = {t.casefold() for t in (skip_terms or []) if t.strip()}
    rules = list(GENERALIZE_RULES)
    if include_case_specific:
        rules.extend(
            {**row, "category": row.get("category", "case")} for row in CASE_SPECIFIC_ALIASES
        )

    hits: list[CoarsenHit] = []
    for rule in rules:
        category = str(rule.get("category", "general"))
        replacement = str(rule["to"])
        for term in rule["from_terms"]:
            if term.casefold() in skipped:
                continue
            pattern = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)
            for match in pattern.finditer(text):
                hits.append(
                    CoarsenHit(
                        original=match.group(),
                        replacement=replacement,
                        category=category,
                        start=match.start(),
                        end=match.end(),
                    )
                )

    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    accepted: list[CoarsenHit] = []
    for hit in hits:
        if any(hit.start < a.end and a.start < hit.end for a in accepted):
            continue
        accepted.append(hit)
    accepted.sort(key=lambda h: h.start)

    # Collapse adjacent hits that rewrite to the same phrase (AH-64 + Apache).
    merged: list[CoarsenHit] = []
    for hit in accepted:
        if (
            merged
            and merged[-1].replacement == hit.replacement
            and hit.start <= merged[-1].end + 1
        ):
            prev = merged[-1]
            merged[-1] = CoarsenHit(
                original=text[prev.start : hit.end],
                replacement=hit.replacement,
                category=hit.category,
                start=prev.start,
                end=hit.end,
            )
        else:
            merged.append(hit)

    pieces: list[str] = []
    cursor = 0
    for hit in merged:
        pieces.append(text[cursor : hit.start])
        pieces.append(hit.replacement)
        cursor = hit.end
    pieces.append(text[cursor:])
    return CoarsenResult(text="".join(pieces), hits=merged)


def find_available_coarsenings(text: str) -> list[ReviewItem]:
    """Rules that would fire on this text (for the review pane before apply)."""
    preview = apply_coarsen(text)
    return [
        ReviewItem(
            kind="coarsen_available",
            text=hit.original,
            detail=f"→ {hit.replacement}",
            category=hit.category,
            replacement=hit.replacement,
        )
        for hit in preview.hits
    ]


def build_review(
    *,
    date_offset_days: int,
    date_shifts: list[dict],
    coarsen_hits: list[dict],
    available: list[ReviewItem],
) -> list[dict]:
    """Flatten review rows for the UI."""
    rows: list[dict] = []
    if date_offset_days:
        rows.append(
            {
                "kind": "date_shifted",
                "text": f"All dates moved by {date_offset_days:+d} days",
                "detail": f"{len(date_shifts)} date(s) rewritten",
                "category": "date",
                "replacement": "",
            }
        )
        for shift in date_shifts:
            rows.append(
                {
                    "kind": "date_shifted",
                    "text": shift["original"],
                    "detail": f"→ {shift['shifted']}",
                    "category": "date",
                    "replacement": shift["shifted"],
                }
            )
    for hit in coarsen_hits:
        rows.append(
            {
                "kind": "coarsened",
                "text": hit["original"],
                "detail": f"→ {hit['replacement']}",
                "category": hit.get("category", ""),
                "replacement": hit["replacement"],
            }
        )
    # Available but not yet applied (e.g. user skipped coarsen this run).
    applied = {(h["original"].casefold(), h["replacement"]) for h in coarsen_hits}
    for item in available:
        key = (item.text.casefold(), item.replacement)
        if key in applied:
            continue
        rows.append(
            {
                "kind": item.kind,
                "text": item.text,
                "detail": item.detail,
                "category": item.category,
                "replacement": item.replacement,
            }
        )
    return rows
