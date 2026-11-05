"""Adapter-facing state: one SessionEngine per session, counts only.

The adapter (Hermes plugin) holds one AdapterState for the process. Audit
data is metadata-only: counts and statuses, never message content or
original values.
"""

from __future__ import annotations

import threading

from privacy_pass.policy import DEFAULT_POLICY, Policy
from privacy_pass.registry import SessionEngine


class AdapterState:
    def __init__(self, policy: Policy = DEFAULT_POLICY):
        self.policy = policy
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionEngine] = {}
        self.stats: dict[str, int] = {
            "requests_sanitized": 0,
            "requests_blocked": 0,
            "detections": 0,
            "failures": 0,
            "auxiliary_calls": 0,
        }

    def session(self, session_id: str) -> SessionEngine:
        with self._lock:
            engine = self._sessions.get(session_id)
            if engine is None:
                engine = SessionEngine(self.policy)
                self._sessions[session_id] = engine
            return engine

    def restore(self, session_id: str, text: str) -> str:
        return self.session(session_id).restore_response(text)

    def record(self, **counters: int) -> None:
        with self._lock:
            for key, value in counters.items():
                self.stats[key] = self.stats.get(key, 0) + value
