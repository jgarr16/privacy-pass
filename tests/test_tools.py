"""Tool-call protection: argument policy, result sanitization, block guard."""

import json

from hooks import make_pre_tool_call_handler, make_transform_tool_result_handler
from middleware import make_tool_request_handler
from privacy_pass.engine import AdapterState
from privacy_pass.policy import Policy

NAME = "Jane Doe"


def state_with_protect() -> AdapterState:
    return AdapterState(Policy(protect_list=(NAME,)))


def test_external_free_text_args_aliased():
    handler = make_tool_request_handler(state_with_protect())
    out = handler(
        tool_name="web_search",
        args={"query": f"Contact {NAME} about the merger"},
        session_id="s1",
    )
    assert out is not None
    assert NAME not in json.dumps(out["args"])
    assert "query" in out["args"]


def test_urls_and_paths_never_rewritten():
    handler = make_tool_request_handler(state_with_protect())
    url = f"https://example.com/{NAME}"
    out = handler(
        tool_name="web_extract",
        args={"url": url, "query": NAME},
        session_id="s1",
    )
    assert out["args"]["url"] == url  # destination untouched
    assert NAME not in out["args"]["query"]


def test_local_tools_untouched():
    handler = make_tool_request_handler(state_with_protect())
    args = {"path": f"/Users/x/{NAME}.txt", "query": NAME}
    out = handler(tool_name="read_file", args=args, session_id="s1")
    assert out is None  # local tool: raw args stay local


def test_unknown_tool_untouched():
    handler = make_tool_request_handler(state_with_protect())
    out = handler(tool_name="mcp__whatever", args={"text": NAME}, session_id="s1")
    assert out is None


def test_tool_result_local_gets_full_policy():
    handler = make_transform_tool_result_handler(state_with_protect())
    out = handler(
        tool_name="read_file",
        args={"path": "/x"},
        result=f"Meeting notes: {NAME} will lead.",
        session_id="s1",
    )
    assert out is not None
    assert NAME not in out
    assert "<Protected" in out


def test_tool_result_external_structured_only():
    handler = make_transform_tool_result_handler(state_with_protect())
    out = handler(
        tool_name="web_search",
        args={"query": "x"},
        result="Profile of Random Author, contact 212-88-3456.",
        session_id="s1",
    )
    # Structured-only on web results: the SSN is aliased; third-party NER
    # names are left readable (documented boundary — full NER on web pages
    # would alias unrelated people and destroy usefulness).
    assert "212-88-3456" not in out
    assert "Random Author" in out


def test_tool_result_external_protect_list_still_applies():
    # A user-protected value is aliased even in web results: the protect
    # list is tier 1 and applies everywhere.
    handler = make_transform_tool_result_handler(state_with_protect())
    out = handler(
        tool_name="web_search",
        args={"query": "x"},
        result=f"Profile of {NAME}, contact 212-88-3456.",
        session_id="s1",
    )
    assert NAME not in out
    assert "212-88-3456" not in out


def test_tool_result_passthrough_when_clean():
    handler = make_transform_tool_result_handler(state_with_protect())
    out = handler(
        tool_name="read_file",
        args={"path": "/x"},
        result="Nothing sensitive here.",
        session_id="s1",
    )
    assert out is None  # untouched


def test_guard_blocks_external_args_with_raw_protect_value():
    state = state_with_protect()
    state.session("s1").sanitize_request(f"Protect {NAME}")  # seed registry
    guard = make_pre_tool_call_handler(state)
    out = guard(
        tool_name="web_search",
        args={"query": f"email {NAME} directly"},
        session_id="s1",
    )
    assert out is not None
    assert out["action"] == "block"
    assert NAME not in out["message"]  # never echo the value
    assert state.stats["tool_calls_blocked"] == 1


def test_guard_ignores_local_tools_and_clean_args():
    state = state_with_protect()
    guard = make_pre_tool_call_handler(state)
    assert guard(tool_name="read_file", args={"path": NAME}, session_id="s1") is None
    assert guard(tool_name="web_search", args={"query": "weather"}, session_id="s1") is None
