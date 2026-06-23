"""Tests for sync.set_merged_names (API-applied merged event names)."""

from datetime import time

from opentrack_admin import sync
from opentrack_admin.events import EventMergeGroup, EventSchedule


class _FakeAPI:
    def __init__(self, events):
        self._events = events
        self.patches = []

    def get_events(self, comp_id, limit=200):
        return self._events

    def patch_event(self, event, **fields):
        self.patches.append((event["event_id"], fields))
        event.update(fields)


def _group(primary_cat, other_cats, event_code, csv_event):
    primary = EventSchedule(category=primary_cat, event=csv_event, start_time=time(17, 0))
    others = [EventSchedule(category=c, event=csv_event, start_time=time(17, 0))
              for c in other_cats]
    return EventMergeGroup(primary=primary, others=others)


def test_sets_combined_name_on_primary():
    # Live primary still carries its single-category name.
    events = [
        {"event_id": "T02", "event_code": "60H", "category": "G11",
         "name": "G11 60 meter hekk", "url": "u"},
    ]
    api = _FakeAPI(events)
    groups = [_group("G11", ["G12", "J12", "G13"], "60H", "60H")]

    updated, errors = sync.set_merged_names(api, "comp1", groups)

    assert errors == []
    assert updated == 1
    assert api.patches == [("T02", {"name": "G/J 11-13 60 meter hekk"})]


def test_idempotent_when_name_already_combined():
    events = [
        {"event_id": "T02", "event_code": "60H", "category": "G11",
         "name": "G/J 11-13 60 meter hekk", "url": "u"},
    ]
    api = _FakeAPI(events)
    groups = [_group("G11", ["G12", "J12", "G13"], "60H", "60H")]

    updated, errors = sync.set_merged_names(api, "comp1", groups)

    assert updated == 0
    assert api.patches == []


def test_matches_primary_by_event_code_and_category():
    # 400m primary is a Rekrutt category that normalizes to G10 in OpenTrack.
    events = [
        {"event_id": "T01", "event_code": "400", "category": "G10",
         "name": "G10 400 meter", "url": "u"},
    ]
    api = _FakeAPI(events)
    groups = [_group("G-Rekrutt", ["J-Rekrutt"], "400", "400m")]

    updated, errors = sync.set_merged_names(api, "comp1", groups)

    assert updated == 1
    assert api.patches == [("T01", {"name": "G/J 10 400 meter"})]


def test_reports_error_when_primary_missing():
    api = _FakeAPI([])  # no live events
    groups = [_group("G11", ["G12"], "60H", "60H")]

    updated, errors = sync.set_merged_names(api, "comp1", groups)

    assert updated == 0
    assert len(errors) == 1
    assert errors[0][0] == "G 11-12 60 meter hekk"
