"""Tests for field-event attempt configuration, incl. the BT ball throw.

Ball throw (BT, "Liten ball") is a horizontal throw with a fixed attempt count
(3 for recruits), so it must drive max_field_attempts/cut like the other throws
rather than falling back to OpenTrack's 6-attempt default.
"""

from datetime import time

from opentrack_admin import sync
from opentrack_admin.events import (
    AttemptConfig,
    EventSchedule,
    is_horizontal_field_event,
)


def test_ball_throw_is_a_horizontal_field_event():
    assert is_horizontal_field_event("BT")


def test_recruit_ball_throw_uses_three_attempts_no_cut():
    cfg = AttemptConfig.for_category("G10")
    assert (cfg.attempts, cfg.field_cut) == (3, 0)


class _FakeAPI:
    def __init__(self, events):
        self._events = events
        self.patches = []

    def get_events(self, comp_id, limit=200):
        return self._events

    def patch_event(self, event, **fields):
        self.patches.append((event["event_id"], fields))
        event.update(fields)


def test_set_event_times_sets_recruit_ball_throw_attempts():
    events = [
        {"event_id": "F08", "event_code": "BT", "category": "G10",
         "name": "G10 Liten ball", "url": "u",
         "max_field_attempts": 6, "cut_after_round": 3},
    ]
    api = _FakeAPI(events)
    schedules = [EventSchedule(category="G-Rekrutt", event="BT", start_time=time(17, 25))]

    updated, errors = sync.set_event_times(api, "comp1", schedules)

    assert errors == []
    assert updated == 1
    _, fields = api.patches[0]
    assert fields["max_field_attempts"] == 3
    assert fields["cut_after_round"] == 0
