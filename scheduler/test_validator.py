"""Tests for the event-layout validator.

The CSV layout is the agent's merge decision: a row lists the categories that run
together at one time/venue. The validator checks coverage, per-athlete and per-venue
conflicts, track ordering and the age-merge rules against the raw atoms, without
re-deriving any grouping.
"""

import pytest

from scheduler.constraint_validator import (
    ConstraintViolation,
    validate_event_schedule,
)
from scheduler.dtos import EventScheduleRow
from scheduler.models import Athlete, Category, Event, EventType, get_venue_for_event
import scheduler.models as models


def _atom(event_type: EventType, cat: Category) -> Event:
    return Event(
        id=f"{event_type.value}_{cat.value}",
        event_type=event_type,
        age_category=cat,
        start_time="2026-06-24T17:00:00",
        duration_minutes=5,
        personnel_required=2,
        priority_weight=1,
    )


def _row(group_id, event_type, cats, start, end, venue=None) -> EventScheduleRow:
    if venue is None:
        venue = get_venue_for_event(event_type, cats[0])
    return EventScheduleRow(
        event_group_id=group_id,
        event_type=event_type,
        categories=",".join(c.value for c in cats),
        venue=venue,
        start_time=start,
        end_time=end,
    )


@pytest.fixture(autouse=True)
def _arena():
    models.ARENA = models.ARENAS["valhall"]
    models.ACTIVE_SECONDARY_VENUES = set()
    models.SHARED_VENUE_GROUPS = []
    models.STICKY_VENUES = True
    yield


def test_agent_custom_merge_passes():
    # Two atoms the agent chooses to run as ONE field group, plus a separate one.
    atoms = [
        _atom(EventType.sp, Category.j13),
        _atom(EventType.sp, Category.j14),
        _atom(EventType.sp, Category.g15),
    ]
    athletes = [Athlete("A", [atoms[0]]), Athlete("B", [atoms[1]]), Athlete("C", [atoms[2]])]
    rows = [
        _row("merged", EventType.sp, [Category.j13, Category.j14], "17:00", "17:20"),
        _row("solo", EventType.sp, [Category.g15], "17:20", "17:40"),
    ]
    validate_event_schedule(rows, atoms, athletes)  # no raise


def test_missing_atom_fails_coverage():
    atoms = [_atom(EventType.sp, Category.j13), _atom(EventType.sp, Category.j14)]
    athletes = [Athlete("A", [atoms[0]]), Athlete("B", [atoms[1]])]
    rows = [_row("r", EventType.sp, [Category.j13], "17:00", "17:20")]  # J14 unplaced
    with pytest.raises(ConstraintViolation, match="Missing schedule entries"):
        validate_event_schedule(rows, atoms, athletes)


def test_unknown_atom_fails():
    atoms = [_atom(EventType.sp, Category.j13)]
    athletes = [Athlete("A", [atoms[0]])]
    rows = [_row("r", EventType.sp, [Category.j13, Category.j14], "17:00", "17:20")]
    with pytest.raises(ConstraintViolation, match="no registered athletes"):
        validate_event_schedule(rows, atoms, athletes)


def test_athlete_conflict_across_rows_fails():
    # One athlete in two different event atoms whose rows overlap in time.
    sp = _atom(EventType.sp, Category.j13)
    lj = _atom(EventType.lj, Category.j13)
    athletes = [Athlete("A", [sp, lj])]
    rows = [
        _row("sp", EventType.sp, [Category.j13], "17:00", "17:20"),
        _row("lj", EventType.lj, [Category.j13], "17:10", "17:30"),
    ]
    with pytest.raises(ConstraintViolation, match="Athlete conflict for A"):
        validate_event_schedule(rows, [sp, lj], athletes)


def test_athlete_serial_rows_pass():
    # Non-overlapping rows with adequate recovery (>=10 min for 13+) pass.
    sp = _atom(EventType.sp, Category.j13)
    lj = _atom(EventType.lj, Category.j13)
    athletes = [Athlete("A", [sp, lj])]
    rows = [
        _row("sp", EventType.sp, [Category.j13], "17:00", "17:20"),
        _row("lj", EventType.lj, [Category.j13], "17:30", "17:50"),
    ]
    validate_event_schedule(rows, [sp, lj], athletes)  # no raise


def test_athlete_recovery_under_10min_13plus_fails():
    # A 13+ athlete with <10 min between consecutive events has too little
    # recovery — hard failure.
    sp = _atom(EventType.sp, Category.j13)
    lj = _atom(EventType.lj, Category.j13)
    athletes = [Athlete("A", [sp, lj])]
    rows = [
        _row("sp", EventType.sp, [Category.j13], "17:00", "17:20"),
        _row("lj", EventType.lj, [Category.j13], "17:25", "17:45"),  # 5 min gap
    ]
    with pytest.raises(ConstraintViolation, match="recovery time for A"):
        validate_event_schedule(rows, [sp, lj], athletes)


def test_athlete_recovery_under_10min_senior_fails():
    # Seniors/masters are in the 13+ group too.
    sp = _atom(EventType.sp, Category.ks)
    lj = _atom(EventType.lj, Category.ks)
    athletes = [Athlete("A", [sp, lj])]
    rows = [
        _row("sp", EventType.sp, [Category.ks], "17:00", "17:20"),
        _row("lj", EventType.lj, [Category.ks], "17:28", "17:48"),  # 8 min gap
    ]
    with pytest.raises(ConstraintViolation, match="recovery time for A"):
        validate_event_schedule(rows, [sp, lj], athletes)


def test_athlete_recovery_under13_no_rule():
    # The recovery rule applies only to 13+; younger athletes may run back-to-back.
    sp = _atom(EventType.sp, Category.j12)
    lj = _atom(EventType.lj, Category.j12)
    athletes = [Athlete("A", [sp, lj])]
    rows = [
        _row("sp", EventType.sp, [Category.j12], "17:00", "17:20"),
        _row("lj", EventType.lj, [Category.j12], "17:20", "17:40"),  # 0 min gap
    ]
    validate_event_schedule(rows, [sp, lj], athletes)  # no raise


def test_athlete_recovery_13_14_no_warn(capsys):
    # 13-14: >=10 min passes with no warning (the <15 min warn is 15+ only).
    sp = _atom(EventType.sp, Category.j14)
    lj = _atom(EventType.lj, Category.j14)
    athletes = [Athlete("A", [sp, lj])]
    rows = [
        _row("sp", EventType.sp, [Category.j14], "17:00", "17:20"),
        _row("lj", EventType.lj, [Category.j14], "17:32", "17:52"),  # 12 min gap
    ]
    validate_event_schedule(rows, [sp, lj], athletes)
    assert "recovery" not in capsys.readouterr().out.lower()


def test_athlete_recovery_15plus_under_15min_warns(capsys):
    # 15+: a 10-14 min gap passes but emits a soft warning.
    sp = _atom(EventType.sp, Category.j15)
    lj = _atom(EventType.lj, Category.j15)
    athletes = [Athlete("A", [sp, lj])]
    rows = [
        _row("sp", EventType.sp, [Category.j15], "17:00", "17:20"),
        _row("lj", EventType.lj, [Category.j15], "17:32", "17:52"),  # 12 min gap
    ]
    validate_event_schedule(rows, [sp, lj], athletes)  # no raise
    out = capsys.readouterr().out.lower()
    assert "recovery" in out and "a" in out


def test_athlete_recovery_15plus_15min_ok(capsys):
    # 15+ with >=15 min: no failure, no warning.
    sp = _atom(EventType.sp, Category.j15)
    lj = _atom(EventType.lj, Category.j15)
    athletes = [Athlete("A", [sp, lj])]
    rows = [
        _row("sp", EventType.sp, [Category.j15], "17:00", "17:20"),
        _row("lj", EventType.lj, [Category.j15], "17:35", "17:55"),  # 15 min gap
    ]
    validate_event_schedule(rows, [sp, lj], athletes)
    assert "recovery" not in capsys.readouterr().out.lower()


def test_venue_conflict_fails():
    a = _atom(EventType.sp, Category.j13)
    b = _atom(EventType.sp, Category.j14)
    athletes = [Athlete("A", [a]), Athlete("B", [b])]
    rows = [
        _row("r1", EventType.sp, [Category.j13], "17:00", "17:20"),
        _row("r2", EventType.sp, [Category.j14], "17:10", "17:30"),  # same circle, overlaps
    ]
    with pytest.raises(ConstraintViolation, match="Venue conflict"):
        validate_event_schedule(rows, [a, b], athletes)


def test_track_11_14_with_15_17_passes():
    # 11-14 may share a track heat with 15-17 (only seniors are off-limits).
    j13 = _atom(EventType.m60, Category.j13)
    j16 = _atom(EventType.m60, Category.j16)
    athletes = [Athlete("A", [j13]), Athlete("B", [j16])]
    rows = [_row("h", EventType.m60, [Category.j13, Category.j16], "17:00", "17:05")]
    validate_event_schedule(rows, [j13, j16], athletes)  # no raise


def test_track_11_14_with_senior_fails():
    # 11-14 with an adult senior (18+) is forbidden on track.
    j13 = _atom(EventType.m60, Category.j13)
    ms = _atom(EventType.m60, Category.ms)
    athletes = [Athlete("A", [j13]), Athlete("B", [ms])]
    rows = [_row("h", EventType.m60, [Category.j13, Category.ms], "17:00", "17:05")]
    with pytest.raises(ConstraintViolation, match="18-19/Senior/Masters"):
        validate_event_schedule(rows, [j13, ms], athletes)


def test_field_11_14_with_15_17_passes():
    # Same age mix as above but a FIELD event: allowed.
    j13 = _atom(EventType.hj, Category.j13)
    j16 = _atom(EventType.hj, Category.j16)
    athletes = [Athlete("A", [j13]), Athlete("B", [j16])]
    rows = [_row("g", EventType.hj, [Category.j13, Category.j16], "17:00", "17:20")]
    validate_event_schedule(rows, [j13, j16], athletes)  # no raise


def test_field_merges_any_age_passes():
    # Field events may merge across any age boundary: Rekrutt + Senior in one group.
    rek = _atom(EventType.lj, Category.j10)
    sr = _atom(EventType.lj, Category.ks)
    athletes = [Athlete("A", [rek]), Athlete("B", [sr])]
    rows = [_row("g", EventType.lj, [Category.j10, Category.ks], "17:00", "17:20")]
    validate_event_schedule(rows, [rek, sr], athletes)  # no raise


def test_track_rekrutt_with_older_fails():
    rek = _atom(EventType.m60, Category.j10)
    j12 = _atom(EventType.m60, Category.j12)
    athletes = [Athlete("A", [rek]), Athlete("B", [j12])]
    rows = [_row("h", EventType.m60, [Category.j10, Category.j12], "17:00", "17:05")]
    with pytest.raises(ConstraintViolation, match="Rekrutt mixed with older"):
        validate_event_schedule(rows, [rek, j12], athletes)


def test_track_11_14_with_masters_fails():
    j13 = _atom(EventType.m60, Category.j13)
    mv = _atom(EventType.m60, Category.mv60_64)
    athletes = [Athlete("A", [j13]), Athlete("B", [mv])]
    rows = [_row("h", EventType.m60, [Category.j13, Category.mv60_64], "17:00", "17:05")]
    with pytest.raises(ConstraintViolation, match="18-19/Senior/Masters"):
        validate_event_schedule(rows, [j13, mv], athletes)


def test_track_heat_over_eight_fails():
    # 9 athletes across two 60m categories in one heat exceeds the lane cap.
    j13 = _atom(EventType.m60, Category.j13)
    j14 = _atom(EventType.m60, Category.j14)
    athletes = [Athlete(f"j13_{i}", [j13]) for i in range(5)]
    athletes += [Athlete(f"j14_{i}", [j14]) for i in range(4)]
    rows = [_row("h", EventType.m60, [Category.j13, Category.j14], "17:00", "17:05")]
    with pytest.raises(ConstraintViolation, match="exceeding the 8-lane cap"):
        validate_event_schedule(rows, [j13, j14], athletes)


def test_duration_column_optional():
    # EventScheduleRow built without duration_minutes derives it from the window.
    a = _atom(EventType.sp, Category.j13)
    row = _row("r", EventType.sp, [Category.j13], "17:00", "17:18")
    assert row.duration_minutes == 18
    validate_event_schedule([row], [a], [Athlete("A", [a])])


def test_track_ordering_violation_fails():
    m60 = _atom(EventType.m60, Category.j15)
    m200 = _atom(EventType.m200, Category.j15)
    athletes = [Athlete("A", [m60]), Athlete("B", [m200])]
    rows = [
        _row("r200", EventType.m200, [Category.j15], "17:00", "17:05"),
        _row("r60", EventType.m60, [Category.j15], "17:10", "17:15"),  # 60m after 200m
    ]
    with pytest.raises(ConstraintViolation, match="Track event ordering violation"):
        validate_event_schedule(rows, [m60, m200], athletes)


def test_hurdles_mix_distances_within_capacity_passes():
    # 60m hekk: G11(6.5m,68), G12(7m,76.2), J12(7m,68), G13(7.5m,76.2) — 4 distinct
    # setups need 3 gutter lanes, leaving 5 of 8 for 5 athletes. Fits as one heat.
    g11 = _atom(EventType.m60_hurdles, Category.g11)
    g12 = _atom(EventType.m60_hurdles, Category.g12)
    j12 = _atom(EventType.m60_hurdles, Category.j12)
    g13 = _atom(EventType.m60_hurdles, Category.g13)
    athletes = [
        Athlete("a", [g11]), Athlete("b", [g12]),
        Athlete("c", [j12]), Athlete("d", [j12]), Athlete("e", [g13]),
    ]
    rows = [_row("h", EventType.m60_hurdles,
                 [Category.g11, Category.g12, Category.j12, Category.g13],
                 "17:00", "17:05")]
    validate_event_schedule(rows, [g11, g12, j12, g13], athletes)  # no raise


def test_hurdles_exceed_lane_capacity_fails():
    # Force more athletes than lanes-minus-gutters: 3 distinct setups (G11 6.5,
    # G12 7/76.2, G13 7.5) need 2 gutters -> 6 of 8 lanes, but 7 athletes won't fit.
    g11 = _atom(EventType.m60_hurdles, Category.g11)
    g12 = _atom(EventType.m60_hurdles, Category.g12)
    g13 = _atom(EventType.m60_hurdles, Category.g13)
    athletes = [Athlete(f"g11_{i}", [g11]) for i in range(3)]
    athletes += [Athlete(f"g12_{i}", [g12]) for i in range(2)]
    athletes += [Athlete(f"g13_{i}", [g13]) for i in range(2)]
    rows = [_row("h", EventType.m60_hurdles,
                 [Category.g11, Category.g12, Category.g13], "17:00", "17:05")]
    with pytest.raises(ConstraintViolation, match="usable lanes"):
        validate_event_schedule(rows, [g11, g12, g13], athletes)


def test_hurdles_same_distance_different_height_passes():
    # G12 (7m, 76.2cm) and J12 (7m, 68cm): same distance, different heights -> one
    # gutter lane, 2 athletes well within capacity. Allowed.
    g12 = _atom(EventType.m60_hurdles, Category.g12)
    j12 = _atom(EventType.m60_hurdles, Category.j12)
    athletes = [Athlete("A", [g12]), Athlete("B", [j12])]
    rows = [_row("h", EventType.m60_hurdles, [Category.g12, Category.j12], "17:00", "17:05")]
    validate_event_schedule(rows, [g12, j12], athletes)  # no raise


def test_rekrutt_round_out_of_order_passes():
    # A Rekrutt (10yo) round race may run before shorter races so the youngest
    # finish early; the validator warns instead of failing (CONSTRAINTS.md s3).
    m400_g = _atom(EventType.m400, Category.g10)
    m400_j = _atom(EventType.m400, Category.j10)
    m60 = _atom(EventType.m60, Category.j15)
    athletes = [Athlete("A", [m400_g]), Athlete("B", [m400_j]), Athlete("C", [m60])]
    rows = [
        _row("rek400", EventType.m400, [Category.g10, Category.j10], "17:00", "17:05"),
        _row("r60", EventType.m60, [Category.j15], "17:10", "17:15"),
    ]
    validate_event_schedule(rows, [m400_g, m400_j, m60], athletes)
