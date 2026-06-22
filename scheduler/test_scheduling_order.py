"""Tests for track ordering and spacing helpers.

Covers the schedule_2026-06-24 feedback:
  - Rekrutt 400m runs right after the hurdle block, not last.
  - A 400m can't start until hurdles clear the straight (teardown gap).
  - Plain start-position changes cost less than hurdle setup (compression).
"""

from scheduler.functional_scheduler import (
    _get_event_group_sort_key,
    _needs_extra_spacing,
    _track_min_gap_slots,
)
from scheduler.models import Category, Event, EventGroup, EventType
import scheduler.models as models


def _group(event_type: EventType, *cats: Category) -> EventGroup:
    events = [
        Event(
            id=f"{event_type.name}_{c.name}",
            event_type=event_type,
            age_category=c,
            start_time="2026-06-24T17:00:00",
            duration_minutes=5,
            personnel_required=1,
            priority_weight=1,
        )
        for c in cats
    ]
    return EventGroup(id=f"{event_type.name}_grp", event_type=event_type, events=events)


def test_rekrutt_round_sorts_after_sprints_before_older_rounds():
    hurdle = _group(EventType.m100_hurdles, Category.j17)
    rekrutt_400 = _group(EventType.m400, Category.g10, Category.j10)
    senior_3000 = _group(EventType.m3000, Category.ms)
    older_600 = _group(EventType.m600, Category.g12, Category.g14)
    order = [
        g.event_type
        for g in sorted([senior_3000, rekrutt_400, hurdle, older_600], key=_get_event_group_sort_key)
    ]
    assert order[0] == EventType.m100_hurdles  # sprint/hurdle block first
    assert order[1] == EventType.m400          # Rekrutt round right after
    assert order.index(EventType.m400) < order.index(EventType.m600)
    assert order.index(EventType.m400) < order.index(EventType.m3000)


def test_hurdle_teardown_gap_is_two_slots():
    models.ARENA = models.ARENAS["valhall"]  # no sprint→round re-rig
    gap, _ = _track_min_gap_slots(
        _group(EventType.m100_hurdles, Category.j17), _group(EventType.m400, Category.g10), 5
    )
    assert gap == 2  # hurdles must clear the home straight before the 400m


def test_pure_position_change_is_one_slot():
    models.ARENA = models.ARENAS["valhall"]
    gap, _ = _track_min_gap_slots(
        _group(EventType.m400, Category.g10), _group(EventType.m600, Category.g12), 5
    )
    assert gap == 1  # starter move only, no hurdle reconfiguration


def test_same_start_position_needs_no_extra_spacing():
    # m200 and m600 both start at the 200m-to-goal mark (regression for the
    # stale block map that wrongly separated them).
    assert not _needs_extra_spacing(EventType.m200, EventType.m600)
    assert not _needs_extra_spacing(EventType.m1500, EventType.m3000)
