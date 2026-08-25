"""Tests for track lane assignment and the hurdle setup plan.

A missing hurdle spec must fail loudly: the crew cannot rig geometry we do not
have, and a silently dropped heat means a race with no setup card. Lane
assignment must keep an empty gutter between bands that cannot share adjacent
lanes — differing hurdle setups, and block versus standing starts.
"""

import pytest

from scheduler.lane_plan import _assign_lanes, _extract_zones, track_lane_assignments
from scheduler.models import (
    Athlete,
    Category,
    Event,
    EventGroup,
    EventType,
    uses_starting_blocks,
)
from scheduler.types import SchedulingResult


def _event(event_type: EventType, cat: Category) -> Event:
    return Event(
        id=f"{event_type.name}_{cat.name}",
        event_type=event_type,
        age_category=cat,
        start_time="2026-08-26T17:00:00",
        duration_minutes=5,
        personnel_required=2,
        priority_weight=1,
    )


def _group(event_type: EventType, cats: list[Category]) -> EventGroup:
    return EventGroup(
        id="heat",
        event_type=event_type,
        events=[_event(event_type, c) for c in cats],
    )


def _result(groups: list[EventGroup]) -> SchedulingResult:
    """A schedule of one heat per slot, with a single athlete in each event."""
    return SchedulingResult(
        status="ok",
        schedule={
            slot: [{"event": g, "is_start": True}] for slot, g in enumerate(groups)
        },
        total_slots=len(groups),
        total_duration_minutes=5 * len(groups),
        slot_duration_minutes=5,
        events_per_slot={},
        slots_with_events=len(groups),
        optimization_stats=None,
        events=groups,
        athletes=[
            Athlete(name=f"{ev.id} runner", events=[ev])
            for g in groups
            for ev in g.events
        ],
    )


def test_200m_hurdles_uses_gendered_geometry():
    # Boys/men run 18.29 m to first and between; girls/women 16 m then 19 m.
    boys = _extract_zones(_group(EventType.m200_hurdles, [Category.g14]))
    girls = _extract_zones(_group(EventType.m200_hurdles, [Category.j14]))
    assert (boys[0].first_hurdle_m, boys[0].distance_between_m) == (18.29, 18.29)
    assert (girls[0].first_hurdle_m, girls[0].distance_between_m) == (16, 19)


def test_missing_hurdle_spec_raises():
    # 80m hurdles only has G14/J15/J16 geometry; dropping an unknown category
    # silently would print a plan missing that heat entirely.
    group = _group(EventType.m80_hurdles, [Category.g13])
    with pytest.raises(ValueError, match="No hurdle spec"):
        _extract_zones(group)


def test_mixed_distance_heat_yields_one_zone_per_distance():
    zones = _extract_zones(_group(EventType.m60_hurdles, [Category.g11, Category.g13]))
    assert sorted(z.distance_between_m for z in zones) == [6.5, 7.5]


def _lanes(event_type: EventType, cats: list[Category]) -> dict[Category | None, list[int]]:
    """Lane assignment as {category: lanes}, with None collecting the gutters."""
    group = _group(event_type, cats)
    assigned = _assign_lanes(group, {e.id: 1 for e in group.events})
    out: dict[Category | None, list[int]] = {}
    for lane in assigned:
        out.setdefault(lane.category, []).append(lane.lane)
    return out


def test_sprint_heat_mixing_start_types_leaves_a_gutter_lane():
    # 13+ start from blocks, J12 standing, so they cannot be side by side.
    lanes = _lanes(EventType.m60, [Category.j12, Category.g13, Category.g14])
    standing = lanes[Category.j12][0]
    blocks = lanes[Category.g13] + lanes[Category.g14]
    assert lanes[None], "expected a gutter lane between the two start types"
    assert all(abs(lane - standing) > 1 for lane in blocks)


def test_sprint_heat_of_one_start_type_needs_no_gutter():
    lanes = _lanes(EventType.m60, [Category.g13, Category.g14])
    assert None not in lanes


def test_only_heats_with_a_real_lane_requirement_are_exported():
    """A single-band flat heat has nothing to impose, so leave the draw alone."""
    result = _result([
        _group(EventType.m60, [Category.g10, Category.j10]),
        _group(EventType.m600, [Category.g14, Category.j11]),
        _group(EventType.m60, [Category.j12, Category.g13]),
    ])
    exported = {event for event, _, _ in track_lane_assignments(result, 17, 0)}
    assert exported == {"60m"}


def test_middle_distance_never_splits_on_start_type():
    # Nobody uses blocks from 600m, so a mixed-age heat runs unseparated.
    lanes = _lanes(EventType.m600, [Category.j11, Category.g14])
    assert None not in lanes


def test_same_setup_hurdle_categories_share_a_band():
    # J15 and J16 are both 76.2 cm at 8 m and both use blocks: no gutter needed.
    lanes = _lanes(EventType.m80_hurdles, [Category.j15, Category.j16])
    assert None not in lanes


def test_hurdle_spacing_change_still_splits_the_bands():
    # J11 runs 6.5 m spacing and J12 7 m, so the crew needs a lane to work in.
    lanes = _lanes(EventType.m60_hurdles, [Category.j11, Category.j12])
    assert lanes[None], "expected a gutter between the two spacings"


def test_blocks_start_at_13():
    assert not uses_starting_blocks(EventType.m60, Category.j12)
    assert uses_starting_blocks(EventType.m60, Category.j13)


def test_no_blocks_from_600m_up():
    assert not uses_starting_blocks(EventType.m600, Category.ms)
    assert uses_starting_blocks(EventType.m400, Category.ms)
