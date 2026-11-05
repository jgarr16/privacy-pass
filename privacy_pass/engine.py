"""Adapter-facing state: one SessionEngine per session, counts only.

The adapter (Hermes plugin) holds one AdapterState for the process. Audit
data is metadata-only: counts and statuses, never message content or
original values. When a SessionStore is configured, session alias state is
loaded lazily per session (restart continuity) and saved after every
mapping change, in owner-only-permission files.
"""

from __future__ import annotations

import threading

from privacy_pass.policy import DEFAULT_POLICY, Policy
from privacy_pass.registry import SessionEngine
from privacy_pass.storage import SessionStore


class AdapterState:
    def __init__(
        self,
        policy: Policy = DEFAULT_POLICY,
        store: SessionStore | None = None,
    ):
        self.policy = policy
        self.store = store
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionEngine] = {}
        self.stats: dict[str, int] = {
            "requests_sanitized": 0,
            "requests_blocked": 0,
            "detections": 0,
            "failures": 0,
            "auxiliary_calls": 0,
            "tool_arg_detections": 0,
            "tool_result_detections": 0,
            "tool_calls_blocked": 0,
        }

    def session(self, session_id: str) -> SessionEngine:
        with self._lock:
            engine = self._sessions.get(session_id)
            if engine is None:
                engine = SessionEngine(self.policy)
                if self.store is not None:
                    snapshot = self.store.load(session_id)
                    if snapshot:
                        engine.load_snapshot(snapshot)
                    engine.set_on_change(
                        (lambda sid: lambda: self.store.save(sid, engine.snapshot()))(
                            session_id
                        )
                    )
                self._sessions[session_id] = engine
            return engine

    def restore(self, session_id: str, text: str) -> str:
        return self.session(session_id).restore_response(text)

    def record(self, **counters: int) -> None:
        with self._lock:
            for key, value in counters.items():
                self.stats[key] = self.stats.get(key, 0) + value
