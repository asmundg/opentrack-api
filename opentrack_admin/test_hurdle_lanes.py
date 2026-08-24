"""Tests for drawing hurdle lanes from the setup plan.

A hurdle heat mixing setups needs an empty gutter lane between each distinct
(distance, height) pair, so its lanes come from the hurdle plan rather than
from seeding order. The seeded draw would happily put a 76.2 cm and an 84 cm
athlete in adjacent lanes, which the crew cannot rig.
"""

from pathlib import Path

import pytest

from opentrack_admin.api import OpenTrackAPIError
from opentrack_admin.sync import draw_lanes, parse_hurdle_lane_csv

# J15 in lane 3, gutter in 4, G14 in 5 — the 80m hekk plan for a mixed-height heat.
_PLAN_CSV = """event_type,category,lane
80m hekk,J15,3
80m hekk,G14,5
60m,G13,4
"""


@pytest.fixture
def plan(tmp_path: Path) -> Path:
    path = tmp_path / "x_hurdle_lanes.csv"
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


def _api(results):
    return _FakeAPI(
        events=[{
            "event_code": "80H",
            "name": "G14 80 meter hekk",
            "lanes": 8,
            "units": [{"url": "u1", "heat_name": "Race 1 of 1"}],
        }],
        units={"u1": {"results": results}},
        competitors=[
            {"competitor_id": "18", "category": "J15"},
            {"competitor_id": "4", "category": "G14"},
            {"competitor_id": "7", "category": "J15"},
        ],
    )


def test_parses_plan_into_lanes_per_event_and_category(plan):
    assert parse_hurdle_lane_csv(plan) == {
        ("80H", "J15"): [3],
        ("80H", "G14"): [5],
        ("60", "G13"): [4],
    }


def test_mixed_height_heat_keeps_the_gutter_lane_empty(plan):
    api = _api([
        {"bib": "18", "sp": "14.50"},
        {"bib": "4", "sp": "17.20"},
    ])

    updated, errors = draw_lanes(api, "c", parse_hurdle_lane_csv(plan))

    assert (updated, errors) == (1, [])
    assert {r["bib"]: r["lane"] for r in api.patched["u1"]} == {"18": 3, "4": 5}


def test_without_a_plan_the_seeded_draw_puts_them_adjacent(plan):
    """The bug this guards against: seeding alone ignores hurdle setups."""
    api = _api([
        {"bib": "18", "sp": "14.50"},
        {"bib": "4", "sp": "17.20"},
    ])

    draw_lanes(api, "c", None)

    assert {r["bib"]: r["lane"] for r in api.patched["u1"]} == {"18": 4, "4": 5}


def test_fastest_in_a_category_takes_that_category_first_lane(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text("event_type,category,lane\n80m hekk,J15,6\n80m hekk,J15,3\n")
    api = _api([
        {"bib": "18", "sp": "14.50"},
        {"bib": "7", "sp": "13.10"},
    ])

    draw_lanes(api, "c", parse_hurdle_lane_csv(path))

    assert {r["bib"]: r["lane"] for r in api.patched["u1"]} == {"7": 3, "18": 6}


def test_a_stale_plan_fails_loudly_rather_than_reseeding(plan):
    api = _api([
        {"bib": "18", "sp": "14.50"},
        {"bib": "7", "sp": "13.10"},
        {"bib": "4", "sp": "17.20"},
    ])

    _, errors = draw_lanes(api, "c", parse_hurdle_lane_csv(plan))

    assert len(errors) == 1
    assert "regenerate the plan" in errors[0][1]


def test_a_hurdle_heat_missing_from_the_plan_fails_loudly(tmp_path):
    """A stale plan must not silently fall back to an unsafe seeded draw."""
    path = tmp_path / "p.csv"
    path.write_text("event_type,category,lane\n60m hekk,G11,4\n")
    api = _api([
        {"bib": "18", "sp": "14.50"},
        {"bib": "4", "sp": "17.20"},
    ])

    _, errors = draw_lanes(api, "c", parse_hurdle_lane_csv(path))

    assert len(errors) == 1
    assert "regenerate the plan" in errors[0][1]
    assert api.patched == {}
