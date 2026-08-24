"""Tests for field event group durations.

The per-attempt clock slows down as a field shrinks (a lone high jumper is
entitled to 3 minutes between attempts), so a group's window must not scale
linearly with the entry count.
"""

from scheduler.models import Category, Event, EventGroup, EventType


def _event(event_type: EventType, cat: Category, participants: int) -> Event:
    return Event(
        id=f"{event_type.name}_{cat.name}",
        event_type=event_type,
        age_category=cat,
        start_time="2026-08-26T17:00:00",
        duration_minutes=0,
        personnel_required=2,
        priority_weight=1,
        participants=participants,
    )


def _duration(event_type: EventType, pairs: list[tuple[Category, int]]) -> int:
    return EventGroup(
        id="g",
        event_type=event_type,
        events=[_event(event_type, c, n) for c, n in pairs],
    ).duration_minutes


def test_solo_high_jumper_gets_three_minutes_per_attempt():
    # 6 attempts at 3 min plus the 5 min setup, not 6 attempts at 1 min.
    assert _duration(EventType.hj, [(Category.ms, 1)]) == 23


def test_high_jump_pair_is_not_half_of_a_quartet():
    # Two athletes jump at 1.5 min/attempt, four at 1 min, so halving the field
    # does not halve the window.
    pair = _duration(EventType.hj, [(Category.g13, 1), (Category.g14, 1)])
    quartet = _duration(EventType.hj, [(Category.g13, 2), (Category.g14, 2)])
    assert pair == 23
    assert quartet == 29
    assert pair > quartet / 2


def test_solo_thrower_takes_consecutive_attempts():
    # 6 attempts at the 2 min consecutive-attempt clock.
    assert _duration(EventType.tj, [(Category.ms, 1)]) == 12
    # 11-year-olds get 4 attempts.
    assert _duration(EventType.tj, [(Category.j11, 1)]) == 8


def test_full_field_keeps_the_one_minute_rate():
    # Four or more athletes: unchanged from the flat per-attempt model.
    assert _duration(
        EventType.jt,
        [(Category.g14, 1), (Category.g17, 1), (Category.j13, 1), (Category.j16, 2)],
    ) == 30


def test_missing_participant_counts_fall_back_to_precomputed_durations():
    group = EventGroup(
        id="g",
        event_type=EventType.jt,
        events=[_event(EventType.jt, Category.j16, 0)],
    )
    group.events[0].duration_minutes = 12
    assert group.duration_minutes == 12
