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


def make_pre_tool_call_handler(state):
    """``pre_tool_call`` guard: block external tools whose arguments still
    contain a raw protect-list value. This is the only tool-side block
    channel (the tool_request middleware cannot block). The block message
    never echoes the value itself."""
    from privacy_pass.toolpolicy import is_external

    def pre_tool_call(**kwargs):
        tool_name = str(kwargs.get("tool_name") or "")
        args = kwargs.get("args")
        session_id = str(kwargs.get("session_id") or "default")
        if not is_external(tool_name) or not isinstance(args, dict):
            return None
        try:
            engine = state.session(session_id)
            import json as _json

            serialized = _json.dumps(args, ensure_ascii=False, default=str)
            if engine.find_raw_protect_terms(serialized):
                state.record(tool_calls_blocked=1)
                return {
                    "action": "block",
                    "message": (
                        "Privacy Pass blocked this call: a protected value "
                        "would be sent to an external service. Re-run using "
                        "the alias instead of the original value."
                    ),
                }
        except Exception:  # never break tool execution from the guard
            return None
        return None

    return pre_tool_call


def make_transform_tool_result_handler(state):
    """``transform_tool_result`` hook: sanitize tool output before the model
    consumes it again. First string return wins in Hermes; returning None
    leaves the result untouched.

    Policy by destination: local content tools (file reads, session search)
    get the full detector — they can contain the user's own private files.
    External web tools get the structured-only policy — full NER on web
    pages aliases unrelated third-party names and destroys usefulness.
    Failure is fail-open by design: tool results also pass through
    ``llm_request`` sanitization on the next model call.
    """
    from privacy_pass.toolpolicy import is_external

    def transform_tool_result(**kwargs):
        result = kwargs.get("result")
        if not isinstance(result, str) or not result:
            return None
        tool_name = str(kwargs.get("tool_name") or "")
        session_id = str(kwargs.get("session_id") or "default")
        try:
            engine = state.session(session_id)
            if is_external(tool_name):
                res = engine.sanitize_structured_only(result)
            else:
                res = engine.sanitize_request(result)
            if res.detections:
                state.record(tool_result_detections=len(res.detections))
                return res.sanitized_text
            return None
        except Exception:
            return None

    return transform_tool_result
