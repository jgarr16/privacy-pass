"""Tests for the tiered sanitizer pipeline."""

from privacy_pass.sanitizer import reveal, sanitize

SAMPLE = (
    "My name is Jane Smith, I work at Acme Corp, my email is jane@acme.com. "
    "Call me at 555-123-4567."
)


def test_single_name():
    result = sanitize(
        "Please contact Jane Smith about the contract.",
        shift_calendar=False,
        apply_generalize=False,
    )

    assert result.sanitized_text == "Please contact <Person 1> about the contract."
    assert result.mapping == {"<Person 1>": "Jane Smith"}
    assert len(result.detections) == 1
    detection = result.detections[0]
    assert detection.entity_type == "PERSON"
    assert detection.tier == 3
    assert detection.score > 0


def test_two_different_people():
    text = "Jane Smith met with Robert Chen to discuss the acquisition."
    result = sanitize(text, shift_calendar=False, apply_generalize=False)

    assert result.sanitized_text == (
        "<Person 1> met with <Person 2> to discuss the acquisition."
    )
    assert result.mapping == {
        "<Person 1>": "Jane Smith",
        "<Person 2>": "Robert Chen",
    }


def test_same_person_twice_uses_same_placeholder():
    text = "Jane Smith emailed the report. Later, Jane Smith followed up."
    result = sanitize(text, shift_calendar=False, apply_generalize=False)

    assert result.sanitized_text == (
        "<Person 1> emailed the report. Later, <Person 1> followed up."
    )
    assert result.mapping == {"<Person 1>": "Jane Smith"}


def test_email_phone_and_name_together():
    result = sanitize(SAMPLE, shift_calendar=False, apply_generalize=False)

    assert result.sanitized_text == (
        "My name is <Person 1>, I work at <Company 1>, my email is <Email 1>. "
        "Call me at <Phone 1>."
    )
    assert result.mapping == {
        "<Person 1>": "Jane Smith",
        "<Company 1>": "Acme Corp",
        "<Email 1>": "jane@acme.com",
        "<Phone 1>": "555-123-4567",
    }
    for original in result.mapping.values():
        assert original not in result.sanitized_text


def test_protect_list_catches_term_ner_misses():
    text = "The rollout of project bluefin starts Monday."
    result = sanitize(
        text,
        protect_list=["project bluefin"],
        shift_calendar=False,
        apply_generalize=False,
    )

    assert "bluefin" not in result.sanitized_text
    assert result.sanitized_text == "The rollout of <Protected 1> starts Monday."
    assert result.mapping == {"<Protected 1>": "project bluefin"}
    assert result.detections[0].tier == 1
    assert result.detections[0].entity_type == "PROTECTED"


def test_protect_list_beats_ner():
    result = sanitize(
        "Please contact Jane Smith about the contract.",
        protect_list=["Jane Smith"],
        shift_calendar=False,
        apply_generalize=False,
    )

    assert result.sanitized_text == "Please contact <Protected 1> about the contract."
    assert result.mapping == {"<Protected 1>": "Jane Smith"}
    assert [d.tier for d in result.detections] == [1]


def test_protect_list_is_case_insensitive():
    result = sanitize(
        "CHIEF WARRANT OFFICER Smith reported in.",
        protect_list=["Chief Warrant Officer"],
        shift_calendar=False,
        apply_generalize=False,
    )
    assert result.sanitized_text == "<Protected 1> Smith reported in."
    assert result.mapping == {"<Protected 1>": "Chief Warrant Officer"}


def test_protect_list_synonyms_share_placeholder():
    text = "CWO3 Jones and a Chief Warrant Officer met. Then a CHIEF WARRANT OFFICER left."
    result = sanitize(
        text,
        protect_list=["CWO3 | Chief Warrant Officer"],
        shift_calendar=False,
        apply_generalize=False,
    )
    assert "CWO3" not in result.sanitized_text
    assert "Chief Warrant Officer" not in result.sanitized_text
    assert "CHIEF WARRANT OFFICER" not in result.sanitized_text
    assert result.sanitized_text.count("<Protected 1>") == 3
    assert result.mapping == {"<Protected 1>": "CWO3"}


def test_protect_list_name_middle_and_last_first():
    text = (
        "Jane Roberta Smith met Jane R Smith and Jane R. Smith. "
        "Also Smith, Jane R. and SMITH, JANE ROBERTA."
    )
    result = sanitize(
        text,
        protect_list=["Jane Roberta Smith"],
        shift_calendar=False,
        apply_generalize=False,
    )
    assert result.sanitized_text.count("<Protected 1>") == 5
    assert "Jane" not in result.sanitized_text.replace("<Protected 1>", "")
    assert "Smith" not in result.sanitized_text.replace("<Protected 1>", "")


def test_protect_list_does_not_treat_titles_as_names():
    result = sanitize(
        "The Chief Warrant Officer arrived.",
        protect_list=["Chief Warrant Officer"],
        shift_calendar=False,
        apply_generalize=False,
    )
    assert result.sanitized_text == "The <Protected 1> arrived."
    assert "Chief Officer" not in result.sanitized_text


def test_protect_list_phone_ignores_punctuation():
    text = "Call (650) 389-9971 or 650-389-9971 or 6503899971."
    result = sanitize(
        text,
        protect_list=["(650) 389-9971"],
        shift_calendar=False,
        apply_generalize=False,
    )
    assert result.sanitized_text == "Call <Protected 1> or <Protected 1> or <Protected 1>."
    assert list(result.mapping) == ["<Protected 1>"]


def test_protect_list_dates_fold_formats():
    text = "Born January 24, 1967, also 1967-01-24, 1/24/1967, and 24 Jan 1967."
    result = sanitize(
        text,
        protect_list=["January 24, 1967"],
        shift_calendar=False,
        apply_generalize=False,
    )
    assert result.sanitized_text.count("<Protected 1>") == 4
    assert result.mapping == {"<Protected 1>": "January 24, 1967"}
    assert "1967" not in result.sanitized_text.replace("<Protected 1>", "")


def test_protect_list_standalone_first_and_last():
    text = "Patient Doe presented for follow-up. Jane was stable."
    result = sanitize(
        text,
        protect_list=["Jane Roberta Doe"],
        shift_calendar=False,
        apply_generalize=False,
    )
    assert result.sanitized_text == (
        "Patient <Protected 1> presented for follow-up. <Protected 1> was stable."
    )
    assert result.mapping == {"<Protected 1>": "Jane Roberta Doe"}


def test_skip_list_leaves_term_in_place():
    text = "Jane Smith met with Robert Chen to discuss the acquisition."
    result = sanitize(
        text, skip_list=["Jane Smith"], shift_calendar=False, apply_generalize=False
    )

    assert result.sanitized_text == (
        "Jane Smith met with <Person 1> to discuss the acquisition."
    )
    assert result.mapping == {"<Person 1>": "Robert Chen"}


def test_date_shift_keeps_intervals():
    text = "Injury on January 24, 1967. Follow-up on February 7, 1967."
    result = sanitize(
        text,
        shift_calendar=True,
        apply_generalize=False,
        date_offset_days=14,
    )
    assert "January 24, 1967" not in result.sanitized_text
    assert result.date_offset_days == 14
    # 14 days later: Jan 24 → Feb 7, Feb 7 → Feb 21 (gap stays 14 days).
    assert "February 7, 1967" in result.sanitized_text
    assert "February 21, 1967" in result.sanitized_text
    assert len(result.date_shifts) == 2


def test_coarsen_applies_rank_and_platform():
    text = "CWO3 flew the AH-64 Apache at the Palo Alto VA."
    result = sanitize(
        text,
        protect_list=[],
        shift_calendar=False,
        apply_generalize=True,
    )
    assert "CWO3" not in result.sanitized_text
    assert "AH-64" not in result.sanitized_text
    assert "Apache" not in result.sanitized_text
    assert "Palo Alto VA" not in result.sanitized_text
    assert "a senior warrant officer" in result.sanitized_text
    assert result.sanitized_text.count("a military helicopter") == 1
    assert "a West Coast medical center" in result.sanitized_text
    assert any(h["category"] == "place" for h in result.coarsen_hits)


def test_coref_surname_and_possessive_share_token():
    text = "Dr. Robert Chen examined the patient. Chen’s note confirmed the plan."
    result = sanitize(
        text,
        protect_list=["Robert Chen"],
        shift_calendar=False,
        apply_generalize=False,
    )
    assert result.sanitized_text.count("<Protected 1>") >= 2
    assert "Chen" not in result.sanitized_text.replace("<Protected 1>", "")


def test_round_trip():
    result = sanitize(SAMPLE, shift_calendar=False, apply_generalize=False)
    assert reveal(result.sanitized_text, result.mapping) == SAMPLE


def test_round_trip_with_date_shift():
    text = "Born January 24, 1967 in Austin."
    result = sanitize(
        text, shift_calendar=True, apply_generalize=False, date_offset_days=10
    )
    restored = reveal(
        result.sanitized_text, result.mapping, date_shifts=result.date_shifts
    )
    assert "January 24, 1967" in restored


def test_reveal_with_empty_mapping_is_passthrough():
    assert reveal("nothing to do here", {}) == "nothing to do here"
