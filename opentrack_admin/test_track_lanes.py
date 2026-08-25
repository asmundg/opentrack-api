"""Tests for drawing track lanes from the lane plan.

Some heats cannot be laned by seed time alone. A hurdle heat mixing setups
needs an empty gutter lane between each distinct (distance, height) pair, and a
sprint heat mixing block starters with standing ones needs one between the age
bands. Both come from the scheduler's plan; seeding still decides who gets
which lane inside a band.
"""

from pathlib import Path

import pytest

from opentrack_admin.sync import draw_lanes, parse_track_lane_csv

# J15 in lane 3, gutter in 4, G14 in 5 — a mixed-height 80m hekk.
_PLAN_CSV = """event_type,categories,lane
80m hekk,J15,3
80m hekk,G14,5
"""

# J12 starts standing in lane 3, gutter in 4, G13/G14 from blocks in 5 and 6.
_BLOCKS_CSV = """event_type,categories,lane
60m,J12,3
60m,"G13,G14",5
60m,"G13,G14",6
"""


@pytest.fixture
def plan(tmp_path: Path) -> Path:
    path = tmp_path / "x_track_lanes.csv"
    path.write_text(_PLAN_CSV)
    return path


class _FakeAPI:
    def __init__(self, events, units, competitors):
        self._events = events
        self._units = units
        self._competitors = competitors
        self.patched: dict[str, list[dict]] = {}

    def get_events(self, comp_id):
        return self._events

    def get_competitors(self, comp_id):
        return self._competitors

    def get_unit(self, url):
        return self._units[url]

    def patch_unit(self, url, **fields):
        self.patched[url] = fields["results"]


_COMPETITORS = [
    {"competitor_id": "18", "category": "J15"},
    {"competitor_id": "4", "category": "G14"},
    {"competitor_id": "7", "category": "J15"},
    {"competitor_id": "9", "category": "G14"},
    {"competitor_id": "2", "category": "G13"},
    {"competitor_id": "5", "category": "J12"},
]


def _api(results, code="80H", name="G14 80 meter hekk"):
    return _FakeAPI(
        events=[{
            "event_code": code,
            "name": name,
            "lanes": 8,
            "units": [{"url": "u1", "heat_name": "Race 1 of 1"}],
        }],
        units={"u1": {"results": results}},
        competitors=_COMPETITORS,
    )


def _lanes(api):
    return {r["bib"]: r["lane"] for r in api.patched["u1"]}


def test_parses_plan_into_lanes_per_band(plan):
    assert parse_track_lane_csv(plan) == {("80H", "J15"): [3], ("80H", "G14"): [5]}


def test_mixed_height_heat_keeps_the_gutter_lane_empty(plan):
    api = _api([{"bib": "18", "sp": "14.50"}, {"bib": "4", "sp": "17.20"}])

    updated, errors = draw_lanes(api, "c", parse_track_lane_csv(plan))

    assert (updated, errors) == (1, [])
    assert _lanes(api) == {"18": 3, "4": 5}


def test_without_a_plan_the_seeded_draw_puts_them_adjacent(plan):
    """The bug this guards against: seeding alone ignores lane requirements."""
    api = _api([{"bib": "18", "sp": "14.50"}, {"bib": "4", "sp": "17.20"}])

    draw_lanes(api, "c", None)

    assert _lanes(api) == {"18": 4, "4": 5}


def test_standing_starter_is_separated_from_the_block_starters(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text(_BLOCKS_CSV)
    api = _api(
        [
            {"bib": "5", "sp": None},     # J12, standing start
            {"bib": "9", "sp": "7.98"},   # G14, blocks
            {"bib": "2", "sp": "9.55"},   # G13, blocks
        ],
        code="60",
        name="J12 60 meter",
    )

    draw_lanes(api, "c", parse_track_lane_csv(path))

    # Lane 4 stays empty between the standing starter and the block starters.
    assert _lanes(api) == {"5": 3, "9": 5, "2": 6}


def test_fastest_in_a_band_takes_the_most_favoured_lane(tmp_path):
    """Lanes within a band are interchangeable, so seeding orders them."""
    path = tmp_path / "p.csv"
    path.write_text(_BLOCKS_CSV)
    api = _api(
        [
            {"bib": "5", "sp": None},
            {"bib": "9", "sp": "9.55"},   # G14 now the slower of the pair
            {"bib": "2", "sp": "7.98"},
        ],
        code="60",
        name="J12 60 meter",
    )

    draw_lanes(api, "c", parse_track_lane_csv(path))

    assert _lanes(api) == {"5": 3, "2": 5, "9": 6}


def test_a_stale_plan_fails_loudly_rather_than_reseeding(plan):
    api = _api([
        {"bib": "18", "sp": "14.50"},
        {"bib": "7", "sp": "13.10"},
        {"bib": "4", "sp": "17.20"},
    ])

    _, errors = draw_lanes(api, "c", parse_track_lane_csv(plan))

    assert len(errors) == 1
    assert "regenerate the plan" in errors[0][1]
    assert api.patched == {}


def test_an_athlete_missing_from_the_plan_fails_loudly(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text("event_type,categories,lane\n80m hekk,J15,3\n")
    api = _api([{"bib": "18", "sp": "14.50"}, {"bib": "4", "sp": "17.20"}])

    _, errors = draw_lanes(api, "c", parse_track_lane_csv(path))

    assert len(errors) == 1
    assert "regenerate it" in errors[0][1]
    assert api.patched == {}


def test_heats_absent_from_the_plan_still_use_the_seeded_draw(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text("event_type,categories,lane\n60m hekk,G11,4\n")
    api = _api([{"bib": "18", "sp": "14.50"}, {"bib": "4", "sp": "17.20"}])

    draw_lanes(api, "c", parse_track_lane_csv(path))

    assert _lanes(api) == {"18": 4, "4": 5}


def test_another_heat_of_the_same_distance_is_left_alone(tmp_path):
    """Heats share an event code, so a plan for one must not capture the other."""
    path = tmp_path / "p.csv"
    path.write_text(_BLOCKS_CSV)
    api = _FakeAPI(
        events=[{
            "event_code": "60",
            "name": "G10 60 meter",
            "lanes": 8,
            "units": [{"url": "u1", "heat_name": "Race 1 of 1"}],
        }],
        units={"u1": {"results": [{"bib": "30", "sp": None}, {"bib": "31", "sp": None}]}},
        competitors=[
            {"competitor_id": "30", "category": "G6"},
            {"competitor_id": "31", "category": "J8"},
        ],
    )

    updated, errors = draw_lanes(api, "c", parse_track_lane_csv(path))

    assert (updated, errors) == (1, [])
    assert _lanes(api) == {"30": 4, "31": 5}
