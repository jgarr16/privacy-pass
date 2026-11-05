"""``transform_llm_output`` hook: restore aliases in user-facing text.

Display-side failures are fail-open on purpose: showing a placeholder
instead of the original value is a UX issue, never a privacy leak. The exact
return shape must be verified against the installed Hermes release; when the
payload is unrecognized the hook returns None and leaves the reply alone.
Restored text is for display only and must never be sent back out.
"""

from __future__ import annotations

_RESPONSE_KEYS = ("assistant_response", "text", "response")


def make_transform_llm_output_handler(state):
    def transform_llm_output(**kwargs):
        session_id = str(kwargs.get("session_id") or "default")
        for key in _RESPONSE_KEYS:
            value = kwargs.get(key)
            if isinstance(value, str):
                try:
                    return {key: state.restore(session_id, value)}
                except Exception:  # never break the display path
                    return None
        return None

    return transform_llm_output
