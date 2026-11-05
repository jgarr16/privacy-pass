"""Session registry: stable aliases, idempotency, bounded restoration."""

from privacy_pass.policy import Policy
from privacy_pass.registry import SessionEngine


def make_engine(**kwargs) -> SessionEngine:
    return SessionEngine(Policy(**kwargs))


def test_same_value_same_alias_across_calls():
    engine = make_engine(protect_list=("Jane Doe",))
    first = engine.sanitize_request("Jane Doe will join at noon.")
    second = engine.sanitize_request("Email Jane Doe the summary.")
    alias = next(a for a in first.mapping if a.startswith("<Protected"))
    assert alias in second.sanitized_text
    assert first.mapping[alias] == "Jane Doe"


def test_distinct_values_distinct_aliases():
    engine = make_engine(protect_list=("Jane Doe", "John Smith"))
    result = engine.sanitize_request("Jane Doe and John Smith met.")
    people = {a for a in result.mapping if a.startswith("<Protected")}
    assert len(people) == 2


def test_idempotent_on_own_output():
    engine = make_engine(protect_list=("Jane Doe",))
    first = engine.sanitize_request("Jane Doe's email is jane.doe@example.com")
    second = engine.sanitize_request(first.sanitized_text)
    assert second.sanitized_text == first.sanitized_text


def test_new_values_get_new_numbers_across_calls():
    engine = make_engine(protect_list=("Jane Doe", "John Smith"))
    first = engine.sanitize_request("Jane Doe called.")
    second = engine.sanitize_request("John Smith called too.")
    assert "<Protected 1>" in first.sanitized_text
    assert "<Protected 2>" in second.sanitized_text


def test_bare_first_name_reuses_full_name_alias():
    engine = make_engine(protect_list=("Jane Doe",))
    first = engine.sanitize_request("Jane Doe will attend.")
    second = engine.sanitize_request("Jane will attend too.")
    alias = next(a for a in first.mapping if a.startswith("<Protected"))
    assert alias in second.sanitized_text


def test_ssn_formats_share_alias():
    # 212-88-3456 is synthetic but passes the recognizer's validity rules;
    # presidio deliberately rejects canonical placeholders like 123-45-6789.
    engine = make_engine()
    first = engine.sanitize_request("SSN: 212-88-3456")
    second = engine.sanitize_request("SSN: 212883456")
    assert first.sanitized_text == second.sanitized_text
    assert first.sanitized_text != "SSN: 212-88-3456"


def test_restore_roundtrip():
    engine = make_engine(protect_list=("Jane Doe",))
    result = engine.sanitize_request("Tell Jane Doe about the update.")
    restored = engine.restore_response(result.sanitized_text)
    assert "Jane Doe" in restored
    assert "<Protected" not in restored


def test_unknown_alias_left_alone():
    engine = make_engine(protect_list=("Jane Doe",))
    engine.sanitize_request("Jane Doe called.")
    assert engine.restore_response("Who is <Person 99>?") == "Who is <Person 99>?"


def test_stable_alias_across_five_turns():
    engine = make_engine(protect_list=("Jane Doe",))
    first = engine.sanitize_request("Jane Doe has SSN 212-88-3456.")
    alias_name = next(a for a in first.mapping if a.startswith("<Protected"))
    alias_ssn = next(a for a in first.mapping if a.startswith("<SSN"))
    for turn in range(2, 6):
        again = engine.sanitize_request(f"Turn {turn}: Jane Doe, SSN 212-88-3456.")
        assert alias_name in again.sanitized_text
        assert alias_ssn in again.sanitized_text


def test_builtin_skip_terms_reduce_ner_noise():
    engine = make_engine()
    result = engine.sanitize_request("SSN: 212-88-3456")
    assert result.sanitized_text.startswith("SSN: ")  # the word survives
    assert "212-88-3456" not in result.sanitized_text  # the value does not
