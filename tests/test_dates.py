"""Unit tests for date shifting."""

from privacy_pass.dates import shift_dates, unshift_dates


def test_shift_preserves_interval():
    text = "Start January 1, 2000. End January 15, 2000."
    result = shift_dates(text, offset_days=10)
    assert result.offset_days == 10
    assert "January 1, 2000" not in result.text
    assert "January 11, 2000" in result.text
    assert "January 25, 2000" in result.text


def test_unshift_restores_originals():
    text = "Seen on 1967-01-24 and again on 1/24/1967."
    result = shift_dates(text, offset_days=5)
    restored = unshift_dates(result.text, result.shifts)
    assert "1967-01-24" in restored
    assert "1/24/1967" in restored
