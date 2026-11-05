"""Session-scoped alias registry: stable placeholders across turns.

Guarantees:

- A value detected in any turn of a session keeps the same placeholder for
  the whole session, and a placeholder is never reassigned to a new value.
- Sanitizing already-aliased text is a no-op (idempotency contract): aliases
  are passed through the skip list and reused, never re-detected.
- ``restore_response`` substitutes only exact, known aliases; unknown
  placeholder-like text (``<Person 99>``) is left untouched.
- Restored text must never be sent back out; restoration is display-only and
  callers (adapters) are responsible for that boundary.
"""

from __future__ import annotations

import re
import threading

from privacy_pass.policy import DEFAULT_POLICY, Policy
from privacy_pass.sanitizer import (
    TIER_PROTECT_LIST,
    TIER_STRUCTURED,
    SanitizeResult,
    reveal,
    sanitize,
)

_ALIAS_RE = re.compile(r"<([A-Za-z]+) (\d+)>")

# Structured-only scope for machine-composed text (system prompts, tool
# definitions): protect list + structured recognizers, no open-ended NER.
_STRUCTURED_TIERS = frozenset({TIER_PROTECT_LIST, TIER_STRUCTURED})


class SessionEngine:
    """One session's alias state. Safe for concurrent turns."""

    def __init__(self, policy: Policy = DEFAULT_POLICY):
        self.policy = policy
        self._lock = threading.Lock()
        self._identity_to_alias: dict[tuple[str, str], str] = {}
        self._alias_to_original: dict[str, str] = {}
        self._counters: dict[str, int] = {}
        self._on_change = None

    def sanitize_request(self, text: str) -> SanitizeResult:
        """Sanitize one provider-bound text with session-stable aliases."""
        return self._run(text, tiers=None)

    def sanitize_structured_only(self, text: str) -> SanitizeResult:
        """Protect list + structured types only — for machine-composed text
        (system prompts) where open-ended NER would alias tool names and
        brands. User PII enters via conversation messages, which always get
        the full policy."""
        return self._run(text, tiers=_STRUCTURED_TIERS)

    def _run(self, text: str, tiers: frozenset[int] | None) -> SanitizeResult:
        with self._lock:
            result = sanitize(
                text,
                protect_list=list(self.policy.protect_list),
                skip_list=[*self.policy.skip_list, *self._alias_literals()],
                shift_calendar=self.policy.shift_calendar,
                apply_generalize=self.policy.apply_generalize,
                existing_aliases=dict(self._identity_to_alias),
                counter_seeds=dict(self._counters),
                tiers=tiers,
            )
            self._identity_to_alias.update(result.alias_assignments)
            for alias, original in result.mapping.items():
                self._alias_to_original.setdefault(alias, original)
            self._absorb_counters()
            self._seed_namepart_aliases()
            changed = bool(result.alias_assignments)
        if changed and self._on_change is not None:
            try:
                self._on_change()
            except Exception:  # persistence must never break sanitization
                pass
        return result

    def restore_response(self, text: str) -> str:
        """Restore exact known aliases for local display. Never re-sent."""
        with self._lock:
            return reveal(text, dict(self._alias_to_original))

    def status(self) -> dict:
        with self._lock:
            return {"aliases": len(self._alias_to_original)}

    # -- persistence (restart continuity) ----------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "version": 1,
                "identity_to_alias": {
                    f"{etype}|{ident}": alias
                    for (etype, ident), alias in self._identity_to_alias.items()
                },
                "alias_to_original": dict(self._alias_to_original),
                "counters": dict(self._counters),
            }

    def load_snapshot(self, snapshot: dict) -> None:
        with self._lock:
            if not isinstance(snapshot, dict):
                return
            for key, alias in (snapshot.get("identity_to_alias") or {}).items():
                etype, _, ident = str(key).partition("|")
                if etype and ident and isinstance(alias, str):
                    self._identity_to_alias[(etype, ident)] = alias
            for alias, original in (snapshot.get("alias_to_original") or {}).items():
                if isinstance(alias, str) and isinstance(original, str):
                    self._alias_to_original.setdefault(alias, original)
            for word, number in (snapshot.get("counters") or {}).items():
                if isinstance(number, int):
                    self._counters[word] = max(self._counters.get(word, 0), number)
            self._seed_namepart_aliases()

    def find_raw_protect_terms(self, text: str) -> int:
        """Count protect-list values appearing verbatim in text. Returns a
        count only — the values themselves must never be logged or echoed."""
        if not text:
            return 0
        lowered = text.casefold()
        return sum(
            1
            for term in self.policy.protect_list
            if term.strip() and term.strip().casefold() in lowered
        )

    def set_on_change(self, callback) -> None:
        """Register a persistence callback, invoked (without the lock held)
        after every mutation that changes the mapping."""
        self._on_change = callback

    # -- internals ---------------------------------------------------------

    def _alias_literals(self) -> list[str]:
        """Existing aliases as skip terms so they are never re-detected."""
        return list(self._alias_to_original)

    def _absorb_counters(self) -> None:
        for alias in self._alias_to_original:
            match = _ALIAS_RE.fullmatch(alias)
            if match:
                word, number = match.group(1), int(match.group(2))
                self._counters[word] = max(self._counters.get(word, 0), number)

    def _seed_namepart_aliases(self) -> None:
        """A bare first/last name later in the session reuses the full
        name's alias (NER often tags "Jane" alone)."""
        for (etype, ident), alias in list(self._identity_to_alias.items()):
            if etype not in {"PERSON", "PROTECTED"} or not ident.startswith("name:"):
                continue
            body = ident.split(":", 1)[1]
            if "|" not in body:
                continue
            first, last = body.split("|", 1)
            for part in (first, last):
                self._identity_to_alias.setdefault((etype, f"namepart:{part}"), alias)
