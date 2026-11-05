"""``llm_request`` middleware: rewrite the complete provider-bound request.

Hermes middleware is fail-open by design — a raised exception is logged and
the raw request proceeds down the chain. Fail-closed is therefore implemented
inside this handler: every error path returns a request whose conversation
content is replaced by a notice, so unverified content is never sent.

Non-text content parts (images, attachments) are left untouched: they are
outside v1 egress protection and are documented as such, not claimed as
covered.
"""

from __future__ import annotations

import copy
import json

_BLOCK_NOTICE = (
    "[Privacy Pass] This request was blocked before sending: the privacy "
    "layer could not verify and rewrite the outbound content. No message "
    "text was transmitted."
)

# Keys that carry conversation or tool content; dropped from a blocked
# request. Everything else (model, stream settings, ...) passes through.
_CONTENT_KEYS = ("messages", "input", "prompt", "tools", "tool_choice")


def make_llm_request_handler(state):
    """Build the middleware callback bound to an AdapterState."""

    def on_llm_request(**kwargs):
        request = kwargs.get("request")
        session_id = str(kwargs.get("session_id") or "default")
        try:
            if not isinstance(request, dict):
                raise TypeError("request is not a mapping")
            engine = state.session(session_id)
            rewritten = copy.deepcopy(request)
            detections = 0
            if "messages" in rewritten:
                rewritten["messages"], n = _sanitize_messages(
                    rewritten["messages"], engine
                )
                detections += n
            if "input" in rewritten:
                rewritten["input"], n = _sanitize_input(rewritten["input"], engine)
                detections += n
            state.record(requests_sanitized=1, detections=detections)
            return {
                "request": rewritten,
                "source": "privacy-pass",
                "reason": "sanitized outbound request",
            }
        except Exception as exc:  # fail closed on any error, log type only
            state.record(requests_blocked=1, failures=1)
            return {
                "request": _blocked_request(request),
                "source": "privacy-pass",
                "reason": f"fail-closed: {type(exc).__name__}",
            }

    return on_llm_request


def _sanitize_messages(messages, engine):
    if not isinstance(messages, list):
        raise TypeError("messages is not a list")
    out = []
    detections = 0
    for msg in messages:
        if not isinstance(msg, dict):
            raise TypeError("message entry is not a mapping")
        msg = dict(msg)
        msg["content"], n = _sanitize_content(msg.get("content"), engine)
        detections += n
        tool_calls = msg.get("tool_calls")
        if tool_calls is not None:
            msg["tool_calls"], n = _sanitize_tool_calls(tool_calls, engine)
            detections += n
        out.append(msg)
    return out, detections


def _sanitize_input(value, engine):
    """Responses API form: a string, or a list of message items."""
    if isinstance(value, str):
        result = engine.sanitize_request(value)
        return result.sanitized_text, len(result.detections)
    if isinstance(value, list):
        out = []
        detections = 0
        for item in value:
            if not isinstance(item, dict):
                raise TypeError("input entry is not a mapping")
            item = dict(item)
            item["content"], n = _sanitize_content(item.get("content"), engine)
            detections += n
            out.append(item)
        return out, detections
    raise TypeError("input is neither a string nor a list")


def _sanitize_content(content, engine):
    """Sanitize string content or a list of content parts."""
    if content is None:
        return content, 0
    if isinstance(content, str):
        result = engine.sanitize_request(content)
        return result.sanitized_text, len(result.detections)
    if isinstance(content, list):
        out = []
        detections = 0
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                result = engine.sanitize_request(part["text"])
                part = {**part, "text": result.sanitized_text}
                detections += len(result.detections)
            elif isinstance(part, str):
                result = engine.sanitize_request(part)
                part = result.sanitized_text
                detections += len(result.detections)
            # Non-text parts (images/attachments) pass through untouched:
            # outside v1 egress protection by documented boundary.
            out.append(part)
        return out, detections
    raise TypeError(f"unsupported content type: {type(content).__name__}")


def _sanitize_tool_calls(tool_calls, engine):
    """Sanitize string leaves of assistant tool_call arguments (JSON).

    Tool-argument policy is refined later; until then, arguments that cannot
    be parsed and rewritten fail the whole request (fail closed).
    """
    if not isinstance(tool_calls, list):
        raise TypeError("tool_calls is not a list")
    out = []
    detections = 0
    for call in tool_calls:
        if not isinstance(call, dict):
            raise TypeError("tool_call is not a mapping")
        call = copy.deepcopy(call)
        function = call.get("function")
        if isinstance(function, dict) and isinstance(function.get("arguments"), str):
            try:
                parsed = json.loads(function["arguments"])
            except json.JSONDecodeError as exc:
                raise TypeError("tool_call arguments are not valid JSON") from exc
            sanitized, n = _sanitize_json_strings(parsed, engine)
            function["arguments"] = json.dumps(sanitized)
            detections += n
        out.append(call)
    return out, detections


def _sanitize_json_strings(value, engine):
    if isinstance(value, str):
        result = engine.sanitize_request(value)
        return result.sanitized_text, len(result.detections)
    if isinstance(value, list):
        out, total = [], 0
        for item in value:
            new_item, n = _sanitize_json_strings(item, engine)
            out.append(new_item)
            total += n
        return out, total
    if isinstance(value, dict):
        out, total = {}, 0
        for key, item in value.items():
            new_item, n = _sanitize_json_strings(item, engine)
            out[key] = new_item
            total += n
        return out, total
    return value, 0


def _blocked_request(request):
    """A provider-bound request that carries no conversation content."""
    if not isinstance(request, dict):
        request = {}
    blocked = {k: v for k, v in request.items() if k not in _CONTENT_KEYS}
    blocked["messages"] = [{"role": "system", "content": _BLOCK_NOTICE}]
    return blocked
