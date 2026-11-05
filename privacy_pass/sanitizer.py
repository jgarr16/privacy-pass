"""Tiered PII detection and reversible placeholder sanitization.

Pipeline tiers (each produces candidate detections, merged and resolved by
tier priority, then confidence, then span length):

  Tier 1 — Deterministic: the caller's always-protect list, exact match.
  Tier 2 — Structured:   emails, phone numbers, SSNs, credit cards, IPs.
  Tier 3 — Named entities: people, organizations, locations via spaCy NER.
  Tier 4 — Semantic:     local-LLM detection (stub, not implemented yet).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from privacy_pass.coarsen import apply_coarsen
from privacy_pass.dates import shift_dates

TIER_PROTECT_LIST = 1
TIER_STRUCTURED = 2
TIER_NER = 3
TIER_SEMANTIC = 4  # reserved for the future semantic tier

# Presidio entity type -> word used in placeholders like "<Person 1>".
_PLACEHOLDER_WORDS: dict[str, str] = {
    "PROTECTED": "Protected",
    "PERSON": "Person",
    "ORGANIZATION": "Company",
    "LOCATION": "Location",
    "EMAIL_ADDRESS": "Email",
    "PHONE_NUMBER": "Phone",
    "US_SSN": "SSN",
    "CREDIT_CARD": "Card",
    "IP_ADDRESS": "IP",
}

_STRUCTURED_TYPES = frozenset(
    {"EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN", "CREDIT_CARD", "IP_ADDRESS"}
)
_NER_TYPES = frozenset({"PERSON", "ORGANIZATION", "LOCATION"})


@dataclass(frozen=True)
class Detection:
    """One detected sensitive span in the original text."""

    entity_type: str  # Presidio-style type, or "PROTECTED" for the protect list
    start: int  # character offset in the original text, inclusive
    end: int  # character offset in the original text, exclusive
    text: str
    score: float
    tier: int
    identity: str = ""  # stable key for aliases; empty means use `text`
    canonical: str = ""  # preferred restore value from the protect list


@dataclass
class SanitizeResult:
    sanitized_text: str
    mapping: dict[str, str]  # placeholder -> original value
    detections: list[Detection]
    date_offset_days: int = 0
    date_shifts: list[dict] = field(default_factory=list)
    coarsen_hits: list[dict] = field(default_factory=list)
    # (entity_type, identity) -> placeholder, for session-scoped registries
    alias_assignments: dict[tuple[str, str], str] = field(default_factory=dict)


def sanitize(
    text: str,
    protect_list: list[str] | None = None,
    skip_list: list[str] | None = None,
    *,
    shift_calendar: bool = True,
    apply_generalize: bool = True,
    date_offset_days: int | None = None,
    existing_aliases: dict[tuple[str, str], str] | None = None,
    counter_seeds: dict[str, int] | None = None,
    tiers: frozenset[int] | None = None,
) -> SanitizeResult:
    """Replace sensitive spans in `text` with stable placeholders.

    Within one call, the same original value always maps to the same
    placeholder and distinct values never share one. `skip_list` terms are
    left unchanged even if a later tier would have flagged them.

    When enabled, calendar dates are shifted by one shared offset and
    curated coarsen rules rewrite identifying phrases before aliasing.

    `existing_aliases` maps (entity_type, identity) to a placeholder already
    assigned in an enclosing session; matching values reuse that placeholder
    instead of a new one, and `counter_seeds` sets the starting number per
    placeholder word so session-wide placeholders stay unique. Both default
    to empty, which keeps single-call behavior unchanged. `tiers` restricts
    detection to a subset of tiers (e.g. protect list + structured only);
    None keeps all tiers.
    """
    working = text
    date_shifts: list[dict] = []
    coarsen_hits: list[dict] = []
    offset = 0

    if shift_calendar:
        shifted = shift_dates(working, offset_days=date_offset_days)
        working = shifted.text
        offset = shifted.offset_days
        date_shifts = [
            {
                "original": s.original,
                "shifted": s.shifted,
                "start": s.start,
                "end": s.end,
            }
            for s in shifted.shifts
        ]

    if apply_generalize:
        coarsened = apply_coarsen(working, skip_terms=skip_list)
        working = coarsened.text
        coarsen_hits = [
            {
                "original": h.original,
                "replacement": h.replacement,
                "category": h.category,
                "start": h.start,
                "end": h.end,
            }
            for h in coarsened.hits
        ]

    candidates = _protect_list_detections(working, protect_list or [])
    candidates.extend(_presidio_detections(working))
    candidates.extend(_semantic_detections(working))
    candidates = _drop_detections_inside_coarsen(candidates, coarsen_hits)
    candidates = _expand_possessives(working, candidates)
    candidates = _link_person_identities(candidates)
    resolved = _apply_skip_list(_resolve_overlaps(candidates), skip_list or [])
    if tiers is not None:
        resolved = [d for d in resolved if d.tier in tiers]

    placeholder_for: dict[
        tuple[str, str], str
    ] = dict(existing_aliases or {})  # (entity_type, identity) -> placeholder
    counters: dict[str, int] = {}
    mapping: dict[str, str] = {}
    alias_assignments: dict[tuple[str, str], str] = {}
    pieces: list[str] = []
    cursor = 0

    for d in resolved:
        word = _PLACEHOLDER_WORDS[d.entity_type]
        key = (d.entity_type, _detection_identity(d))
        if key not in placeholder_for:
            if word not in counters:
                counters[word] = (counter_seeds or {}).get(word, 0)
            counters[word] += 1
            placeholder_for[key] = f"<{word} {counters[word]}>"
            alias_assignments[key] = placeholder_for[key]
        placeholder = placeholder_for[key]
        if placeholder not in mapping:
            mapping[placeholder] = d.canonical or d.text
        pieces.append(working[cursor : d.start])
        pieces.append(placeholder)
        cursor = d.end
    pieces.append(working[cursor:])

    return SanitizeResult(
        sanitized_text="".join(pieces),
        mapping=mapping,
        detections=resolved,
        date_offset_days=offset,
        date_shifts=date_shifts,
        coarsen_hits=coarsen_hits,
        alias_assignments=alias_assignments,
    )


def _detection_identity(d: Detection) -> str:
    """Stable identity for a detection; formatted variants share one alias.

    SSNs and card numbers are keyed by their digits so `123-45-6789` and
    `123456789` map to the same placeholder. Other types use the detection
    identity, falling back to the casefolded text.
    """
    if d.identity:
        return d.identity
    if d.entity_type in {"US_SSN", "CREDIT_CARD"}:
        digits = _digits_only(d.text)
        if len(digits) >= 7:
            return f"digits:{digits}"
    return d.text.casefold()


def reveal(
    text: str,
    mapping: dict[str, str],
    date_shifts: list[dict] | None = None,
) -> str:
    """Replace every placeholder in `text` with its original value.

    Runs as a single pass, so original values that themselves contain
    placeholder-like text are restored exactly once, without chaining.
    When `date_shifts` is provided, shifted calendar forms are restored too.
    """
    from privacy_pass.dates import unshift_dates

    out = text
    if mapping:
        alternatives = "|".join(
            re.escape(placeholder)
            for placeholder in sorted(mapping, key=len, reverse=True)
        )
        out = re.sub(alternatives, lambda m: mapping[m.group()], out)
    if date_shifts:
        out = unshift_dates(out, date_shifts)
    return out


_DIGIT_SEP = r"[\s().\-./]*"
_NAME_TOKEN = re.compile(r"^[A-Za-z][A-Za-z'\-]*\.?$")
_TITLE_FIRST = frozenset(
    {
        "chief",
        "general",
        "captain",
        "sergeant",
        "colonel",
        "lieutenant",
        "doctor",
        "professor",
        "warrant",
        "officer",
        "honorable",
        "admiral",
        "major",
        "private",
        "corporal",
        "commander",
    }
)
_STANDALONE_NAME_STOP = frozenset(
    {
        "will",
        "may",
        "march",
        "april",
        "june",
        "august",
        "her",
        "his",
        "she",
        "he",
        "they",
        "them",
        "you",
        "your",
        "my",
        "our",
        "who",
        "what",
        "when",
        "where",
        "which",
        "this",
        "that",
        "and",
        "the",
        "for",
        "to",
        "in",
        "on",
        "at",
        "of",
        "dr",
        "mr",
        "mrs",
        "ms",
    }
)
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


def _protect_list_detections(text: str, protect_list: list[str]) -> list[Detection]:
    """Tier 1: case-insensitive phrases, plus digit-flexible phone/SSN forms.

    Put synonyms on one line separated by `|`, e.g. `CWO3 | Chief Warrant Officer`.
    """
    detections: list[Detection] = []
    seen_spans: set[tuple[int, int]] = set()
    for raw in protect_list:
        variants = [part.strip() for part in re.split(r"\s*\|\s*", raw) if part.strip()]
        identity = _protect_identity(variants)
        canonical = variants[0]
        for term in variants:
            for match in _protect_pattern(term).finditer(text):
                span = (match.start(), match.end())
                if span in seen_spans:
                    continue
                seen_spans.add(span)
                detections.append(
                    Detection(
                        entity_type="PROTECTED",
                        start=match.start(),
                        end=match.end(),
                        text=match.group(),
                        score=1.0,
                        tier=TIER_PROTECT_LIST,
                        identity=identity,
                        canonical=canonical,
                    )
                )
    return detections


def _protect_identity(variants: list[str]) -> str:
    for variant in variants:
        parsed_date = _parse_protect_date(variant)
        if parsed_date:
            return f"date:{parsed_date.isoformat()}"
        digits = _digits_only(variant)
        if len(digits) >= 7:
            return f"digits:{digits}"
        parsed = _parse_person_name(variant)
        if parsed:
            first, last = parsed
            return f"name:{first.casefold()}|{last.casefold()}"
    return "phrase:" + "|".join(sorted({v.casefold() for v in variants}))


def _protect_pattern(term: str) -> re.Pattern[str]:
    parsed_date = _parse_protect_date(term)
    if parsed_date:
        return _date_pattern(parsed_date)
    digits = _digits_only(term)
    if len(digits) >= 7:
        body = _DIGIT_SEP.join(re.escape(d) for d in digits)
        return re.compile(rf"(?<!\d)(?:\+?1[\s.\-]*)?\(?{body}(?!\d)")
    parsed = _parse_person_name(term)
    if parsed:
        first, last = parsed
        middle = r"(?:\s+(?:[A-Za-z]\.?|(?-i:[A-Z])[A-Za-z'\-]+))*"
        western = rf"(?<!\w){re.escape(first)}{middle}\s+{re.escape(last)}(?!\w)"
        eastern = rf"(?<!\w){re.escape(last)},\s*{re.escape(first)}{middle}(?!\w)"
        parts = [western, eastern]
        if _allow_standalone_name(first):
            parts.append(rf"(?<!\w){re.escape(first)}(?!\w)")
        if _allow_standalone_name(last):
            parts.append(rf"(?<!\w){re.escape(last)}(?!\w)")
        return re.compile(rf"(?:{'|'.join(parts)})", re.IGNORECASE)
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)


def _allow_standalone_name(part: str) -> bool:
    return len(part) >= 3 and part.casefold() not in _STANDALONE_NAME_STOP


def _parse_protect_date(term: str) -> date | None:
    if _parse_person_name(term):
        return None
    stripped = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", term.strip(), flags=re.IGNORECASE)
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(stripped, fmt).replace(tzinfo=UTC).date()
        except ValueError:
            continue
        if parsed.year > datetime.now(UTC).year + 1:
            parsed = parsed.replace(year=parsed.year - 100)
        if parsed.year < 1800:
            continue
        return parsed
    return None


def _date_pattern(value: date) -> re.Pattern[str]:
    y, m, d = value.year, value.month, value.day
    yy = f"{y % 100:02d}"
    month_long = value.strftime("%B")
    month_short = value.strftime("%b")
    day_u, day_p = str(d), f"{d:02d}"
    mon_u, mon_p = str(m), f"{m:02d}"
    forms = [
        rf"{month_long}\s+{day_u},?\s+{y}",
        rf"{month_short}\.?\s+{day_u},?\s+{y}",
        rf"{day_u}\s+{month_long},?\s+{y}",
        rf"{day_u}\s+{month_short}\.?,?\s+{y}",
        rf"{y}-{mon_p}-{day_p}",
        rf"{y}/{mon_p}/{day_p}",
        rf"{mon_u}/{day_u}/{y}",
        rf"{mon_p}/{day_p}/{y}",
        rf"{mon_u}/{day_u}/{yy}",
        rf"{mon_p}-{day_p}-{y}",
        rf"{y}{mon_p}{day_p}",
    ]
    return re.compile(r"(?<!\w)(?:" + "|".join(forms) + r")(?!\w)", re.IGNORECASE)


def _parse_person_name(term: str) -> tuple[str, str] | None:
    """Return (first, last) for a personal name; otherwise None."""
    term = term.strip()
    if "," in term:
        last, rest = [part.strip() for part in term.split(",", 1)]
        given = rest.split()
        if not last or not given:
            return None
        first = given[0]
        tokens = [*given, last]
    else:
        parts = term.split()
        if len(parts) < 2:
            return None
        first, last = parts[0], parts[-1]
        tokens = parts
    if first.casefold() in _TITLE_FIRST:
        return None
    if not all(_NAME_TOKEN.match(tok) for tok in tokens):
        return None
    if not (first[0].isupper() and last[0].isupper()):
        return None
    return first, last


def _digits_only(term: str) -> str:
    return re.sub(r"\D", "", term)


def _presidio_detections(text: str) -> list[Detection]:
    """Tiers 2 and 3: Presidio's structured recognizers and spaCy NER."""
    results = _get_analyzer().analyze(text=text, language="en")
    detections: list[Detection] = []
    for result in results:
        if result.entity_type in _STRUCTURED_TYPES:
            tier = TIER_STRUCTURED
        elif result.entity_type in _NER_TYPES:
            tier = TIER_NER
        else:
            continue  # DATE_TIME, URLs, etc. are out of MVP scope
        detections.append(
            Detection(
                entity_type=result.entity_type,
                start=result.start,
                end=result.end,
                text=text[result.start : result.end],
                score=result.score,
                tier=tier,
                identity=_ner_identity(result.entity_type, text[result.start : result.end]),
            )
        )
    return detections


def _drop_detections_inside_coarsen(
    detections: list[Detection], coarsen_hits: list[dict]
) -> list[Detection]:
    """Do not re-alias text we already coarsened (e.g. 'West Coast' as Location)."""
    if not coarsen_hits:
        return detections
    replacements = {h["replacement"].casefold() for h in coarsen_hits}
    kept: list[Detection] = []
    for d in detections:
        needle = d.text.casefold()
        if any(needle and needle in rep for rep in replacements):
            continue
        kept.append(d)
    return kept


def _ner_identity(entity_type: str, span: str) -> str:
    if entity_type != "PERSON":
        return ""
    parsed = _parse_person_name(span)
    if parsed:
        first, last = parsed
        return f"name:{first.casefold()}|{last.casefold()}"
    tokens = span.split()
    if len(tokens) == 1 and _allow_standalone_name(tokens[0]):
        return f"namepart:{tokens[0].casefold()}"
    return ""


def _expand_possessives(text: str, detections: list[Detection]) -> list[Detection]:
    """Include a trailing 's / ’s so 'Chen’s note' aliases with 'Chen'."""
    expanded: list[Detection] = []
    for d in detections:
        if d.entity_type not in {"PERSON", "PROTECTED", "ORGANIZATION"}:
            expanded.append(d)
            continue
        end = d.end
        tail = text[end : end + 2]
        if tail in {"'s", "’s"} or end < len(text) and text[end] in {"'", "’"} and end + 1 < len(text) and text[end + 1].lower() == "s":
            end = end + 2
        if end == d.end:
            expanded.append(d)
            continue
        expanded.append(
            Detection(
                entity_type=d.entity_type,
                start=d.start,
                end=end,
                text=text[d.start:end],
                score=d.score,
                tier=d.tier,
                identity=d.identity,
                canonical=d.canonical or d.text,
            )
        )
    return expanded


def _link_person_identities(detections: list[Detection]) -> list[Detection]:
    """One person, one token: bare surname/first name join a full name in-doc."""
    full_names: list[tuple[str, str, str]] = []  # first, last, identity
    for d in detections:
        if d.entity_type not in {"PERSON", "PROTECTED"}:
            continue
        if d.identity.startswith("name:") and "|" in d.identity:
            _, body = d.identity.split(":", 1)
            first, last = body.split("|", 1)
            full_names.append((first, last, d.identity))

    if not full_names:
        return detections

    linked: list[Detection] = []
    for d in detections:
        if d.entity_type not in {"PERSON", "PROTECTED"}:
            linked.append(d)
            continue
        if d.identity.startswith("name:") and "|" in d.identity:
            linked.append(d)
            continue
        part = re.sub(r"['’]s$", "", d.text, flags=re.IGNORECASE).casefold()
        match_id = ""
        for first, last, identity in full_names:
            if part == last or part == first:
                match_id = identity
                break
        if not match_id and d.identity.startswith("namepart:"):
            part = d.identity.split(":", 1)[1]
            for first, last, identity in full_names:
                if part == last or part == first:
                    match_id = identity
                    break
        if match_id:
            linked.append(
                Detection(
                    entity_type=d.entity_type,
                    start=d.start,
                    end=d.end,
                    text=d.text,
                    score=d.score,
                    tier=d.tier,
                    identity=match_id,
                    canonical=d.canonical,
                )
            )
        else:
            linked.append(d)
    return linked


def _semantic_detections(text: str) -> list[Detection]:
    """Tier 4 stub: local-LLM semantic detection. Not implemented for MVP."""
    return []


def _resolve_overlaps(detections: list[Detection]) -> list[Detection]:
    """Keep the strongest candidate per span.

    Priority: lower tier number wins, then higher confidence, then longer
    span. Returned in left-to-right text order.
    """
    ranked = sorted(detections, key=lambda d: (d.tier, -d.score, -(d.end - d.start)))
    accepted: list[Detection] = []
    for d in ranked:
        if not any(d.start < a.end and a.start < d.end for a in accepted):
            accepted.append(d)
    return sorted(accepted, key=lambda d: d.start)


def _apply_skip_list(detections: list[Detection], skip_list: list[str]) -> list[Detection]:
    skipped: set[str] = set()
    for term in skip_list:
        skipped |= _skip_keys(term)
    if not skipped:
        return detections
    return [d for d in detections if not (_skip_keys(d.text) & skipped)]


def _skip_keys(term: str) -> set[str]:
    term = term.strip()
    if not term:
        return set()
    keys = {term.casefold()}
    parsed_date = _parse_protect_date(term)
    if parsed_date:
        keys.add(f"date:{parsed_date.isoformat()}")
    parsed = _parse_person_name(term)
    if parsed:
        first, last = parsed
        keys.add(f"name:{first.casefold()}|{last.casefold()}")
        keys.add(first.casefold())
        keys.add(last.casefold())
    digits = _digits_only(term)
    if len(digits) >= 7:
        keys.add(f"digits:{digits}")
    return keys


_analyzer = None


def _get_analyzer():
    """Lazy-loaded Presidio AnalyzerEngine, so spaCy loads once per process."""
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
        provider = NlpEngineProvider(nlp_configuration=configuration)
        _analyzer = AnalyzerEngine(
            nlp_engine=provider.create_engine(), supported_languages=["en"]
        )
    return _analyzer
