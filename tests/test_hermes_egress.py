"""Day-one gate: fake secrets must never appear in the effective payload.

These tests call the real middleware handler with the documented Hermes
``llm_request`` contract (kwargs in, {"request": ...} out) and inspect the
serialized effective payload — the same proof as a captured provider request.
All identifiers are synthetic.
"""

import json

from middleware import make_llm_request_handler
from privacy_pass.engine import AdapterState

FAKE_NAME = "Jane Doe"
# Synthetic but valid per SSA rules — presidio deliberately rejects canonical
# placeholders like 123-45-6789, so the gate must use a plausible fake.
FAKE_SSN = "212-88-3456"
FAKE_EMAIL = "jane.doe@example.com"
FAKE_SECRETS = (FAKE_NAME, FAKE_SSN, FAKE_EMAIL)


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


def test_gate_display_restore_only():
    state = AdapterState()
    handler = make_llm_request_handler(state)
    out = handler(request=build_request(), session_id="s1")
    alias_text = out["request"]["messages"][-1]["content"]
    restored = state.restore("s1", alias_text)
    assert FAKE_NAME in restored
    assert FAKE_SSN in restored
    assert "<SSN" not in restored
