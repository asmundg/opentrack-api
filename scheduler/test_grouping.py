"""Tests for field event grouping (age-tier merging and tiny-bucket rescue).

Focus: Rekrutt isolation and avoidance of over-wide age merges. These reproduce
the schedule_2026-06-24 issues:
  - Lengde merged Rekrutt (10yo) with G12/J12.
  - Spyd merged G11..G17 into one group instead of <=12 / >=13.
"""

from scheduler.__main__ import group_events_by_type
from scheduler.models import Athlete, Category, Event, EventType, Venue
import scheduler.models as models


def _build(event_type: EventType, counts: dict[Category, int]) -> tuple[list[Event], list[Athlete]]:
    """Build events + athletes for one event type with the given per-category counts."""
    events: list[Event] = []
    athletes: list[Athlete] = []
    for cat, n in counts.items():
        ev = Event(
            id=f"{event_type.name}_{cat.name}",
            event_type=event_type,
            age_category=cat,
            start_time="2026-06-24T17:00:00",
            duration_minutes=6,
            personnel_required=2,
            priority_weight=1,
        )
        events.append(ev)
        for i in range(n):
            athletes.append(Athlete(name=f"{cat.name}_{i}", events=[ev]))
    return events, athletes


def _field_groups(event_type: EventType, counts: dict[Category, int]) -> list[set[str]]:
    """Return the field groups (as sets of category value strings) for one event type."""
    models.ARENA = models.ARENAS["valhall"]
    models.ACTIVE_SECONDARY_VENUES = set()
    events, athletes = _build(event_type, counts)
    groups = group_events_by_type(events, athletes)
    return [
        {e.age_category.value for e in g.events}
        for g in groups
        if models.EventVenueMapping.get(g.event_type) != Venue.TRACK
    ]


def test_lengde_rekrutt_not_mixed_with_older():
    # G-Rekrutt 1, J-Rekrutt 1, G12 2, J12 3
    groups = _field_groups(
        EventType.lj,
        {Category.g10: 1, Category.j10: 1, Category.g12: 2, Category.j12: 3},
    )
    rekrutt = {"G-Rekrutt", "J-Rekrutt"}
    for g in groups:
        assert not (g & rekrutt and g - rekrutt), f"Rekrutt mixed with older: {g}"
    assert {"G-Rekrutt", "J-Rekrutt"} in groups
    assert {"G12", "J12"} in groups


def test_spyd_splits_at_twelve_thirteen_boundary():
    # G11 1, G12 1, J12 2, J13 1, G17 2  -> {G11,G12,J12}=4 and {J13,G17}=3
    groups = _field_groups(
        EventType.jt,
        {Category.g11: 1, Category.g12: 1, Category.j12: 2, Category.j13: 1, Category.g17: 2},
    )
    assert {"G11", "G12", "J12"} in groups
    assert {"J13", "G17"} in groups
    assert len(groups) == 2


def test_diskos_merges_across_boundary_when_both_deficient():
    # J12 2, J13 1, G14 1 -> one group of 4 (both 11-12 and 13-14 are deficient)
    groups = _field_groups(
        EventType.dt,
        {Category.j12: 2, Category.j13: 1, Category.g14: 1},
    )
    assert groups == [{"J12", "J13", "G14"}]


def test_slegge_wide_merge_when_no_alternative():
    # G11 1, J13 1, J17 1, Kvinner Senior 1 -> single group of 4 (all deficient)
    groups = _field_groups(
        EventType.ht,
        {Category.g11: 1, Category.j13: 1, Category.j17: 1, Category.ks: 1},
    )
    assert len(groups) == 1
    assert groups[0] == {"G11", "J13", "J17", "Kvinner Senior"}


def _hurdle_heats(event_type: EventType, counts: dict[Category, int]) -> list[tuple[frozenset[str], int]]:
    """Return hurdle heats (category set, athlete count) with both mix flags on."""
    models.ARENA = models.ARENAS["valhall"]
    models.ACTIVE_SECONDARY_VENUES = set()
    events, athletes = _build(event_type, counts)
    cnt = {e.id: 0 for e in events}
    for a in athletes:
        for e in a.events:
            cnt[e.id] += 1
    groups = group_events_by_type(
        events, athletes, mix_genders_track=True, mix_hurdle_distances=True
    )
    return [
        (frozenset(e.age_category.value for e in g.events), sum(cnt[e.id] for e in g.events))
        for g in groups
    ]


def test_60m_hurdles_balanced_packing_avoids_solo():
    # G11 1, G12 1, G13 1, J12 2 -> two heats, neither a one-person heat
    # (greedy left {G13} alone; balanced packing gives {G11,J12}=3 + {G12,G13}=2).
    heats = _hurdle_heats(
        EventType.m60_hurdles,
        {Category.g11: 1, Category.g12: 1, Category.g13: 1, Category.j12: 2},
    )
    assert len(heats) == 2, heats
    assert all(total >= 2 for _, total in heats), heats


def test_80m_hurdles_respect_hard_15_boundary():
    # G14 (<15) and J15 (>=15) must never share a heat (hard age boundary).
    heats = _hurdle_heats(EventType.m80_hurdles, {Category.g14: 1, Category.j15: 1})
    for cats, _ in heats:
        assert not ({"G14"} <= cats and {"J15"} <= cats), cats

