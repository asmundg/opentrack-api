"""Relay (team event) sizing: heats are counted in teams, not runners."""

from .constraint_validator import _atom_counts, age_merge_errors
from .dtos import EventScheduleRow
from .isonen_parser import _calculate_event_duration
from .models import Athlete, Category, Event, EventType, Venue


def _event(category: Category, entries: int) -> Event:
    return Event(
        id=f"relay_{category.value}",
        event_type=EventType.relay_4x60,
        age_category=category,
        start_time="2026-09-02T19:00:00",
        duration_minutes=5,
        personnel_required=1,
        priority_weight=10,
        entries=entries,
    )


def _row(group_id: str, categories: str) -> EventScheduleRow:
    return EventScheduleRow(
        event_group_id=group_id,
        event_type=EventType.relay_4x60,
        categories=categories,
        venue=Venue.TRACK,
        start_time="19:00",
        end_time="19:05",
    )


def test_relay_heat_is_one_slot_per_team_not_per_runner():
    """Three 4-person teams fill three lanes, so it stays a single 5-min heat."""
    assert _calculate_event_duration(EventType.relay_4x60, Category.stafett_11_12, 3) == 5
    # Counted as 12 runners it would wrongly split into two heats.
    assert _calculate_event_duration(EventType.relay_4x60, Category.stafett_11_12, 12) == 10


def test_atom_counts_uses_teams_for_relays_and_athletes_otherwise():
    relay = _event(Category.stafett_13_14, entries=2)
    sprint = Event(
        id="60m_G11",
        event_type=EventType.m60,
        age_category=Category.g11,
        start_time="2026-09-02T17:00:00",
        duration_minutes=5,
        personnel_required=1,
        priority_weight=10,
        entries=1,
    )
    # Eight runners across the two relay teams, plus one of them in the 60m.
    athletes = [
        Athlete(name=f"Runner {i}", events=[relay]) for i in range(8)
    ] + [Athlete(name="Sprinter", events=[sprint])]

    counts = _atom_counts(athletes, [relay, sprint])
    assert counts[(EventType.relay_4x60, Category.stafett_13_14)] == 2
    assert counts[(EventType.m60, Category.g11)] == 1


def test_merged_relay_classes_pass_lane_cap_on_team_count():
    """Two classes of 3 teams = 6 lanes: legal, though it is 24 runners."""
    events = [
        _event(Category.stafett_11_12, entries=3),
        _event(Category.stafett_13_14, entries=3),
    ]
    athletes = [
        Athlete(name=f"R{i}", events=[events[i % 2]]) for i in range(24)
    ]
    counts = _atom_counts(athletes, events)
    rows = [_row("relay_11-14", "Stafett 11-12,Stafett 13-14")]
    assert age_merge_errors(rows, counts) == []


def test_relay_still_rejects_illegal_age_merge():
    """Rekrutt teams may not share a heat with older ones, same as any track heat."""
    events = [
        _event(Category.stafett_6_10, entries=1),
        _event(Category.stafett_11_12, entries=1),
    ]
    counts = _atom_counts([], events)
    rows = [_row("relay_all", "Stafett 6-10,Stafett 11-12")]
    errors = age_merge_errors(rows, counts)
    assert len(errors) == 1
    assert "Rekrutt" in errors[0]


def test_relay_runs_last_in_track_order():
    from .models import TRACK_DISTANCE_ORDER

    assert TRACK_DISTANCE_ORDER[-1] == EventType.relay_4x60
