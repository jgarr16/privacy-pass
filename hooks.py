"""``transform_llm_output`` hook: restore aliases in user-facing text.

Contract verified against installed Hermes v0.22.7 (``agent/turn_finalizer.py``):
payload keys are ``response_text, session_id, model, platform, turn_id`` and
the hook must return a plain replacement string — the first non-empty string
wins; None or empty leaves the reply unchanged. With ``hold_stream=True`` a
callback that fails withholds the reply entirely, so a display-side error
cannot leak the pre-restore text.

Hermes persists the *restored* text and replays it in the next turn's
history; the ``llm_request`` middleware re-sanitizes that history with the
same session registry, so the round trip stays alias-stable. Restored text
must never be sent anywhere else.
"""

from __future__ import annotations

# response_text is the verified key; the others are forward-compat aliases.
_TEXT_KEYS = ("response_text", "assistant_response", "text", "response")


def make_transform_llm_output_handler(state):
    def transform_llm_output(**kwargs):
        session_id = str(kwargs.get("session_id") or "default")
        for key in _TEXT_KEYS:
            value = kwargs.get(key)
            if isinstance(value, str) and value:
                try:
                    return state.restore(session_id, value)
                except Exception:  # never break the display path
                    return None
        return None

    return transform_llm_output


def make_pre_auxiliary_handler(state):
    """``pre_auxiliary_call`` hook: count auxiliary side-calls (titling,
    compression, vision, approval). Hermes auxiliary calls are observer-only
    territory — no plugin surface can rewrite or block them, so they bypass
    sanitization by construction. We count them (metadata only, no content)
    so /privacy can say so honestly. Returns are ignored by design."""

    def pre_auxiliary_call(**kwargs):
        state.record(auxiliary_calls=1)
        return None

    return pre_auxiliary_call
