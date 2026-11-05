"""/privacy slash command: local status and counts only — no message content."""

from __future__ import annotations


def make_status_handler(state):
    def privacy_status(**kwargs):
        stats = dict(state.stats)
        lines = [
            "Privacy Pass — status",
            f"  mode: {state.policy.mode}",
            f"  requests sanitized: {stats.get('requests_sanitized', 0)}",
            f"  detections: {stats.get('detections', 0)}",
            f"  requests blocked (fail-closed): {stats.get('requests_blocked', 0)}",
            "  storage: in-memory per session; mappings never leave this device",
            "  limits: detection is not complete coverage; attachments are not protected",
        ]
        return "\n".join(lines)

    return privacy_status
