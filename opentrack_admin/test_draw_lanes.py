"""Tests for lane drawing from seeding performances."""

from .sync import lane_preference, parse_seed_performance


def test_lane_preference_works_outwards_from_the_middle():
    assert lane_preference(8) == [4, 5, 3, 6, 2, 7, 1, 8]
    assert lane_preference(6) == [3, 4, 2, 5, 1, 6]
    assert lane_preference(1) == [1]


def test_parse_seed_performance_handles_the_formats_opentrack_emits():
    assert parse_seed_performance("11.65") == 11.65
    assert parse_seed_performance("11,65") == 11.65
    assert parse_seed_performance("1:59.39") == 119.39
    assert parse_seed_performance("1:02:03.5") == 3723.5
    assert parse_seed_performance("") is None
    assert parse_seed_performance(None) is None
    assert parse_seed_performance("DNS") is None


def test_fastest_gets_the_middle_lane_and_unseeded_go_outside():
    rows = [
        {"bib": "15", "sp": "11.65"},
        {"bib": "23", "sp": "11.30"},
        {"bib": "26", "sp": None},
        {"bib": "17", "sp": "13.84"},
    ]
    ordered = sorted(
        rows,
        key=lambda r: (
            parse_seed_performance(r["sp"]) is None,
            parse_seed_performance(r["sp"]) or 0.0,
            r["bib"],
        ),
    )
    lanes = dict(zip([r["bib"] for r in ordered], lane_preference(8)))
    assert lanes == {"23": 4, "15": 5, "17": 3, "26": 6}
