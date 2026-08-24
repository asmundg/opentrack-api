"""Tests for the hurdle setup plan.

A missing hurdle spec must fail loudly: the crew cannot rig geometry we do not
have, and a silently dropped heat means a race with no setup card.
"""

import pytest

from scheduler.hurdle_plan_generator import _extract_zones
from scheduler.models import Category, Event, EventGroup, EventType


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
