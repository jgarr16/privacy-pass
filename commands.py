"""/privacy slash command: local status and counts only — no message content."""

from __future__ import annotations


def make_status_handler(state):
    def privacy_status(**kwargs):
        stats = dict(state.stats)
        protect_count = len(state.policy.protect_list)
        lines = [
            "Privacy Pass — status",
            f"  mode: {state.policy.mode} | protected terms: {protect_count}",
            f"  requests sanitized: {stats.get('requests_sanitized', 0)}",
            f"  detections: {stats.get('detections', 0)}",
            f"  requests blocked (fail-closed): {stats.get('requests_blocked', 0)}",
            "  tools: external free-text args aliased; local tools untouched; "
            f"tool results sanitized ({stats.get('tool_result_detections', 0)} hits, "
            f"{stats.get('tool_calls_blocked', 0)} blocked)",
            "  storage: alias maps in memory + owner-only files under "
            "~/.hermes/plugins_data/privacy-pass/sessions (0600); nothing leaves this device",
            "  limits: detection is not complete coverage; attachments are not protected",
        ]
        auxiliary = stats.get("auxiliary_calls", 0)
        if auxiliary:
            lines.append(
                f"  NOT PROTECTED — {auxiliary} auxiliary side-call(s) bypassed "
                "sanitization (Hermes exposes no rewrite surface for them; set "
                "auxiliary.title_generation.enabled: false to reduce them)"
            )
        return "\n".join(lines)

    return privacy_status
