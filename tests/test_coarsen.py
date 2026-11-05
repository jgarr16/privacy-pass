"""Unit tests for coarsen / generalize application."""

from privacy_pass.coarsen import apply_coarsen


def test_apply_coarsen_rank_and_place():
    text = "CWO3 treated at the Austin VA Clinic after flying a CH-53."
    result = apply_coarsen(text)
    assert "a senior warrant officer" in result.text
    assert "a central Texas medical center" in result.text
    assert "a military helicopter" in result.text
    assert "CWO3" not in result.text
