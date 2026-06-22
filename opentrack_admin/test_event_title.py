"""Tests for deriving discipline codes from OpenTrack event titles."""

import pytest

from opentrack_admin.events import event_code_from_event_title


@pytest.mark.parametrize(
    "title,expected",
    [
        # Merged track titles (the motivating case).
        ("G/J 11-13 60 meter hekk", "60H"),
        ("G 12-14 600 meter", "600m"),
        ("G/J 10 400 meter", "400m"),
        # Single-category titles.
        ("G13 Høyde", "HJ"),
        ("J10 Liten ball", "BT"),
        ("MS 3000 meter", "3000m"),
        # Longest-suffix wins: "Høyde uten tilløp" must beat "Høyde".
        ("Menn Senior Høyde uten tilløp", "SHJ"),
        ("J17 100 meter hekk", "100H"),
        # Round annotations appended without a space are stripped.
        ("G/J 11-13 60 meter hekkRace 1 of 1", "60H"),
        ("G13 HøydePool 1 of 1", "HJ"),
        ("G 12-14 600 meterRace 2 of 3", "600m"),
        # Generic distance not in the explicit vocabulary.
        ("G13 150 meter", "150m"),
    ],
)
def test_event_code_from_event_title(title, expected):
    assert event_code_from_event_title(title) == expected


def test_event_code_from_event_title_unknown():
    assert event_code_from_event_title("Totally Unknown Event") is None
