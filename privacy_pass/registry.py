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
from privacy_pass.sanitizer import SanitizeResult, reveal, sanitize

_ALIAS_RE = re.compile(r"<([A-Za-z]+) (\d+)>")


class SessionEngine:
    """One session's alias state. Safe for concurrent turns."""

    def __init__(self, policy: Policy = DEFAULT_POLICY):
        self.policy = policy
        self._lock = threading.Lock()
        self._identity_to_alias: dict[tuple[str, str], str] = {}
        self._alias_to_original: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def sanitize_request(self, text: str) -> SanitizeResult:
        """Sanitize one provider-bound text with session-stable aliases."""
        with self._lock:
            result = sanitize(
                text,
                protect_list=list(self.policy.protect_list),
                skip_list=[*self.policy.skip_list, *self._alias_literals()],
                shift_calendar=self.policy.shift_calendar,
                apply_generalize=self.policy.apply_generalize,
                existing_aliases=dict(self._identity_to_alias),
                counter_seeds=dict(self._counters),
            )
            self._identity_to_alias.update(result.alias_assignments)
            for alias, original in result.mapping.items():
                self._alias_to_original.setdefault(alias, original)
            self._absorb_counters()
            self._seed_namepart_aliases()
            return result

    def restore_response(self, text: str) -> str:
        """Restore exact known aliases for local display. Never re-sent."""
        with self._lock:
            return reveal(text, dict(self._alias_to_original))

    def status(self) -> dict:
        with self._lock:
            return {"aliases": len(self._alias_to_original)}

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
