"""Day-one gate: fake secrets must never appear in the effective payload.

These tests call the real middleware handler with the documented Hermes
``llm_request`` contract (kwargs in, {"request": ...} out) and inspect the
serialized effective payload — the same proof as a captured provider request.
All identifiers are synthetic.
"""

import json

from middleware import make_llm_request_handler
from privacy_pass.engine import AdapterState
from privacy_pass.policy import Policy

FAKE_NAME = "Jane Doe"
# Synthetic but valid per SSA rules — presidio deliberately rejects canonical
# placeholders like 123-45-6789, so the gate must use a plausible fake.
FAKE_SSN = "212-88-3456"
FAKE_EMAIL = "jane.doe@example.com"
FAKE_SECRETS = (FAKE_NAME, FAKE_SSN, FAKE_EMAIL)
POLICY_WITH_NAME = Policy(protect_list=(FAKE_NAME,))


def build_request() -> dict:
    return {
        "model": "test-model",
        "stream": True,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": (
                    f"Ask {FAKE_NAME} about SSN {FAKE_SSN} "
                    f"or email {FAKE_EMAIL}."
                ),
            },
        ],
    }


def test_gate_secrets_absent_from_effective_payload():
    handler = make_llm_request_handler(AdapterState())
    out = handler(request=build_request(), session_id="s1")
    blob = json.dumps(out["request"])
    for secret in FAKE_SECRETS:
        assert secret not in blob, f"raw secret reached the payload: {secret}"
    assert out["request"]["model"] == "test-model"
    assert "<Person" in blob
    assert "<SSN" in blob
    assert "<Email" in blob


def test_gate_aliases_stable_on_second_turn():
    handler = make_llm_request_handler(AdapterState())
    first = handler(request=build_request(), session_id="s1")
    second = handler(request=build_request(), session_id="s1")
    first_user = first["request"]["messages"][-1]["content"]
    second_user = second["request"]["messages"][-1]["content"]
    assert second_user == first_user


def test_gate_responses_input_form_sanitized():
    handler = make_llm_request_handler(AdapterState())
    out = handler(
        request={"model": "m", "input": f"Email {FAKE_EMAIL}"},
        session_id="s1",
    )
    assert FAKE_EMAIL not in json.dumps(out["request"])


def test_gate_fail_closed_on_malformed_messages():
    handler = make_llm_request_handler(AdapterState())
    request = build_request()
    request["messages"] = "not-a-list"
    out = handler(request=request, session_id="s1")
    blob = json.dumps(out["request"])
    for secret in FAKE_SECRETS:
        assert secret not in blob
    assert out["reason"].startswith("fail-closed")
    assert "blocked" in out["request"]["messages"][0]["content"]


def test_gate_fail_closed_on_non_mapping_request():
    handler = make_llm_request_handler(AdapterState())
    out = handler(request=[1, 2, 3], session_id="s1")
    blob = json.dumps(out["request"])
    for secret in FAKE_SECRETS:
        assert secret not in blob
    assert out["reason"].startswith("fail-closed")


def test_gate_assistant_tool_call_args_sanitized():
    # Protect list makes the name deterministic (NER is probabilistic in
    # some sentence contexts); the SSN relies on structured detection.
    handler = make_llm_request_handler(AdapterState(POLICY_WITH_NAME))
    request = {
        "model": "m",
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": json.dumps(
                                {"query": f"lookup {FAKE_NAME} {FAKE_SSN}"}
                            ),
                        },
                    }
                ],
            }
        ],
    }
    out = handler(request=request, session_id="s1")
    args = json.loads(
        out["request"]["messages"][0]["tool_calls"][0]["function"]["arguments"]
    )
    assert FAKE_NAME not in args["query"]
    assert FAKE_SSN not in args["query"]


def test_gate_non_json_tool_args_fail_closed():
    handler = make_llm_request_handler(AdapterState())
    request = {
        "model": "m",
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "x", "arguments": "{not json"},
                    }
                ],
            }
        ],
    }
    out = handler(request=request, session_id="s1")
    assert out["reason"].startswith("fail-closed")
    blob = json.dumps(out["request"])
    for secret in FAKE_SECRETS:
        assert secret not in blob


def test_gate_display_restore_only():
    state = AdapterState()
    handler = make_llm_request_handler(state)
    out = handler(request=build_request(), session_id="s1")
    alias_text = out["request"]["messages"][-1]["content"]
    restored = state.restore("s1", alias_text)
    assert FAKE_NAME in restored
    assert FAKE_SSN in restored
    assert "<SSN" not in restored


def test_gate_system_prompt_gets_structured_only_policy():
    """Machine-composed system text keeps names/brands intact (NER noise)
    but still loses structured values (SSNs, emails, cards)."""
    handler = make_llm_request_handler(AdapterState())
    request = {
        "model": "m",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Tools: GitHub, Linear. Contact Jane Doe if needed. "
                    f"Test SSN {FAKE_SSN}."
                ),
            },
            {"role": "user", "content": "hi"},
        ],
    }
    out = handler(request=request, session_id="s1")
    system_text = out["request"]["messages"][0]["content"]
    assert FAKE_SSN not in system_text  # structured still sanitized
    assert "<SSN" in system_text
    assert "Jane Doe" in system_text  # NER noise on system text left alone
    assert "GitHub" in system_text
