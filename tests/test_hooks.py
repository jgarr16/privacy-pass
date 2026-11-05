"""``transform_llm_output`` hook contract (verified against installed Hermes
v0.22.7: payload key ``response_text``, plain-string return)."""

from hooks import make_transform_llm_output_handler
from privacy_pass.engine import AdapterState
from privacy_pass.policy import Policy

NAME = "Jane Doe"


def state_with_alias() -> AdapterState:
    state = AdapterState(Policy(protect_list=(NAME,)))
    state.session("s1").sanitize_request(f"{NAME} will attend.")
    return state


def test_returns_plain_string_from_response_text():
    handler = make_transform_llm_output_handler(state_with_alias())
    out = handler(response_text="<Protected 1> will attend.", session_id="s1")
    assert out == f"{NAME} will attend."


def test_none_when_no_recognized_key():
    handler = make_transform_llm_output_handler(state_with_alias())
    assert handler(unrelated="x", session_id="s1") is None


def test_unknown_alias_passes_through_untouched():
    handler = make_transform_llm_output_handler(state_with_alias())
    out = handler(response_text="Who is <Person 99>?", session_id="s1")
    assert out == "Who is <Person 99>?"
