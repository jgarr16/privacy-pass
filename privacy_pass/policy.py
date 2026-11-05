"""Policy configuration for the privacy layer.

Modes are policies, not claims of complete coverage. Dates and destructive
generalization stay off by default (README hard requirement: do not silently
change facts).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Policy:
    mode: str = "personal"  # personal | work | strict
    protect_list: tuple[str, ...] = ()
    skip_list: tuple[str, ...] = ()
    shift_calendar: bool = False
    apply_generalize: bool = False
    # Session ids are isolated by construction; kept here for /privacy status.
    notes: tuple[str, ...] = field(default_factory=tuple)


DEFAULT_POLICY = Policy()
