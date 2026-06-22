"""Constraint validation for manually laid-out event schedules.

The event-overview CSV is the agent's layout: each row places a set of
``(event_type, category)`` atoms at a time window and venue. Listing several
categories in one row simply means they run at the same time/venue ("merging" is a
layout decision, not a property of the data). This module validates that layout
against the raw athlete entries without recomputing any grouping:

- coverage: every atom that has athletes is placed in exactly one row;
- per athlete: an athlete's atoms never overlap in time;
- per venue: rows sharing a venue (or a --shared bucket) never overlap, and event
  types stay contiguous when --sticky is on;
- track ordering: track rows run in distance order;
- age merges: track heats obey the age-mixing rules (field events may merge any ages).

The authoritative occupancy is each row's ``start_time``..``end_time`` window;
``duration_minutes`` is reference-only.
"""

from collections import defaultdict

from .dtos import EventScheduleRow
from . import models as _models
from .models import (
    Athlete,
    Category,
    Event,
    EventType,
    EventVenueMapping,
    MASTERS_CATEGORIES,
    Venue,
    get_category_age_order,
    get_scheduling_venue_keys,
    get_track_event_order,
    hurdle_lane_capacity,
    is_hurdles_event,
    ROUND_EVENTS,
    TRACK_DISTANCE_ORDER,
)


# Age tiers for merge validation, by Category identity.
_REKRUTT: frozenset[Category] = frozenset({Category.g10, Category.j10})
_ELEVEN_FOURTEEN: frozenset[Category] = frozenset({
    Category.g11, Category.g12, Category.g13, Category.g14,
    Category.j11, Category.j12, Category.j13, Category.j14,
})
# Seniors that 11-14 may never share a track heat with (15-17 is allowed).
_EIGHTEEN_PLUS_SR: frozenset[Category] = frozenset({
    Category.g18_19, Category.j18_19, Category.ms, Category.ks,
})

_TRACK_LANE_CAP = 8


class ConstraintViolation(Exception):
    """Raised when a scheduling constraint is violated."""

    pass


def _is_fifa_event(row: EventScheduleRow) -> bool:
    """Check if a row is a FIFA (non-athletic) event such as a break."""
    return row.categories.strip().upper() == Category.fifa.value.upper()


def _row_categories(row: EventScheduleRow) -> list[Category]:
    """Parse a row's comma-separated category values into Category enums."""
    cats: list[Category] = []
    for raw in row.categories.split(','):
        name = raw.strip()
        if not name:
            continue
        try:
            cats.append(Category(name))
        except ValueError as e:
            raise ConstraintViolation(
                f"Row {row.event_group_id} has unknown category '{name}'"
            ) from e
    return cats


def _atom_counts(athletes: list[Athlete]) -> dict[tuple[EventType, Category], int]:
    """Count distinct athletes registered for each (event_type, category) atom."""
    counts: dict[tuple[EventType, Category], int] = defaultdict(int)
    for athlete in athletes:
        seen: set[tuple[EventType, Category]] = set()
        for e in athlete.events:
            key = (e.event_type, e.age_category)
            if key not in seen:
                seen.add(key)
                counts[key] += 1
    return counts


def validate_event_schedule(
    rows: list[EventScheduleRow],
    atom_events: list[Event],
    athletes: list[Athlete],
    *,
    slot_duration_minutes: int = 5,
) -> None:
    """Validate the agent's layout against the raw entries.

    Args:
        rows: event-overview CSV rows (the layout, with merges and times).
        atom_events: the raw (event_type, category) events parsed from the XLSX.
        athletes: athletes with their event atoms.

    Raises:
        ConstraintViolation: if any hard constraint is violated.
    """
    regular_rows = [r for r in rows if not _is_fifa_event(r)]

    rows_by_atom = _validate_coverage(regular_rows, atom_events)

    # Venue conflicts and stickiness include FIFA rows (they occupy space).
    _validate_venue_conflicts(rows)
    if _models.STICKY_VENUES:
        _validate_venue_stickiness(rows)

    _validate_athlete_conflicts(athletes, rows_by_atom)
    _validate_track_ordering(regular_rows)
    _validate_age_merges(regular_rows, _atom_counts(athletes))

    print("✓ All constraints validated successfully")


def _validate_coverage(
    rows: list[EventScheduleRow],
    atom_events: list[Event],
) -> dict[tuple[EventType, Category], EventScheduleRow]:
    """Check every atom is placed exactly once; return the atom -> row map.

    A row covers the atoms formed by its event_type and each of its categories.
    Every atom with registered athletes must be covered exactly once, and a row may
    not reference an atom that has no athletes.
    """
    all_atoms = {(e.event_type, e.age_category) for e in atom_events}

    rows_by_atom: dict[tuple[EventType, Category], EventScheduleRow] = {}
    for row in rows:
        for cat in _row_categories(row):
            key = (row.event_type, cat)
            if key not in all_atoms:
                raise ConstraintViolation(
                    f"Row {row.event_group_id} schedules {row.event_type.value} "
                    f"{cat.value}, which has no registered athletes"
                )
            if key in rows_by_atom:
                raise ConstraintViolation(
                    f"{row.event_type.value} {cat.value} is scheduled twice: in "
                    f"{rows_by_atom[key].event_group_id} and {row.event_group_id}"
                )
            rows_by_atom[key] = row

    missing = all_atoms - set(rows_by_atom)
    if missing:
        labels = ', '.join(
            sorted(f"{et.value} {cat.value}" for et, cat in missing)
        )
        raise ConstraintViolation(f"Missing schedule entries for: {labels}")

    return rows_by_atom


def _validate_venue_conflicts(rows: list[EventScheduleRow]) -> None:
    """Validate that no two rows use the same venue at overlapping times.

    Honors shared-venue groups (set via CLI): event types that share officials or
    equipment fold onto a single conflict key so they cannot overlap even if their
    physical venues differ.
    """
    venue_events: dict[str, list[EventScheduleRow]] = defaultdict(list)
    for row in rows:
        for key in get_scheduling_venue_keys(row.event_type, row.venue):
            venue_events[key].append(row)

    for venue_key, venue_rows in venue_events.items():
        venue_rows.sort(key=lambda r: r.start_time)
        for current, nxt in zip(venue_rows, venue_rows[1:]):
            if nxt.start_time < current.end_time:
                if venue_key.startswith("shared:"):
                    label = f"shared group ({venue_key[len('shared:'):]})"
                else:
                    label = venue_key
                raise ConstraintViolation(
                    f"Venue conflict at {label}: "
                    f"{current.event_group_id} ({current.start_time}-{current.end_time}) "
                    f"overlaps with {nxt.event_group_id} ({nxt.start_time}-{nxt.end_time})"
                )


def _validate_venue_stickiness(rows: list[EventScheduleRow]) -> None:
    """Validate that event types at each non-track venue form contiguous blocks.

    Walks every non-track scheduling venue key in start-time order and ensures no
    event type reappears after a different type has occurred (no DT-HT-DT
    interleaving). Track is exempt; it has its own precedence rules.
    """
    venue_events: dict[str, list[EventScheduleRow]] = defaultdict(list)
    for row in rows:
        for key in get_scheduling_venue_keys(row.event_type, row.venue):
            if key == Venue.TRACK.value:
                continue
            venue_events[key].append(row)

    for venue_key, venue_rows in venue_events.items():
        rows_sorted = sorted(venue_rows, key=lambda r: r.start_time)
        seen: dict[EventType, int] = {}
        for idx, row in enumerate(rows_sorted):
            if row.event_type in seen and seen[row.event_type] != idx - 1:
                prev_idx = seen[row.event_type]
                offender = rows_sorted[prev_idx + 1]
                if venue_key.startswith("shared:"):
                    label = f"shared group ({venue_key[len('shared:'):]})"
                else:
                    label = venue_key
                raise ConstraintViolation(
                    f"Venue stickiness violated at {label}: "
                    f"{row.event_type.value} appears at {rows_sorted[prev_idx].start_time} "
                    f"and again at {row.start_time}, with "
                    f"{offender.event_type.value} ({offender.event_group_id}) "
                    f"at {offender.start_time} in between"
                )
            seen[row.event_type] = idx


def _validate_athlete_conflicts(
    athletes: list[Athlete],
    rows_by_atom: dict[tuple[EventType, Category], EventScheduleRow],
) -> None:
    """Validate that no athlete is placed in two overlapping rows."""
    for athlete in athletes:
        placed: list[EventScheduleRow] = []
        seen_rows: set[str] = set()
        for e in athlete.events:
            row = rows_by_atom.get((e.event_type, e.age_category))
            if row is not None and row.event_group_id not in seen_rows:
                seen_rows.add(row.event_group_id)
                placed.append(row)

        placed.sort(key=lambda r: r.start_time)
        for current, nxt in zip(placed, placed[1:]):
            if nxt.start_time < current.end_time:
                raise ConstraintViolation(
                    f"Athlete conflict for {athlete.name}: "
                    f"{current.event_group_id} ({current.start_time}-{current.end_time}) "
                    f"overlaps with {nxt.event_group_id} ({nxt.start_time}-{nxt.end_time})"
                )


def _is_rekrutt_round_event(row: EventScheduleRow) -> bool:
    """True if the row is a round race (400m etc.) run only by 10-year-olds.

    Rekrutt round events are allowed to run out of strict distance order (e.g. first,
    on a clear track) so the youngest finish early. See CONSTRAINTS.md section 3.
    """
    cats = _row_categories(row)
    return (
        row.event_type in ROUND_EVENTS
        and bool(cats)
        and all(c in _REKRUTT for c in cats)
    )


def _validate_track_ordering(rows: list[EventScheduleRow]) -> None:
    """Validate track event ordering: track rows run in distance order.

    Distance order is hard, with one exception: a Rekrutt round race (e.g. a
    10-year-old 400m) may run out of order for welfare, which only warns.
    younger-categories-first within a distance is also a soft policy (a warning).
    """
    track_rows = [r for r in rows if r.event_type in TRACK_DISTANCE_ORDER]
    if len(track_rows) <= 1:
        return

    track_rows.sort(key=lambda r: r.start_time)
    for current, nxt in zip(track_rows, track_rows[1:]):
        current_order = get_track_event_order(current.event_type)
        next_order = get_track_event_order(nxt.event_type)
        if next_order < current_order:
            # Rekrutt round-event exception: a 10-year-old round race may run early
            # (out of strict distance order) so the youngest finish first. Warn only.
            if _is_rekrutt_round_event(current):
                print(
                    f"⚠️  Track ordering (Rekrutt exception): {current.event_type.value} "
                    f"({current.categories}) runs out of distance order before "
                    f"{nxt.event_type.value}"
                )
                continue
            raise ConstraintViolation(
                f"Track event ordering violation: "
                f"{nxt.event_type.value} (order {next_order}) "
                f"cannot come after {current.event_type.value} (order {current_order}). "
                "Track events must follow distance order: "
                f"{', '.join(e.value for e in TRACK_DISTANCE_ORDER)}"
            )

        if current.event_type == nxt.event_type:
            current_youngest = min(
                (get_category_age_order(c) for c in _row_categories(current)),
                default=99,
            )
            next_youngest = min(
                (get_category_age_order(c) for c in _row_categories(nxt)),
                default=99,
            )
            if next_youngest < current_youngest:
                print(
                    f"⚠️  Track age ordering (soft): {current.event_type.value} has "
                    f"younger categories ({nxt.categories}) after older "
                    f"({current.categories})"
                )


def _validate_age_merges(
    rows: list[EventScheduleRow],
    counts: dict[tuple[EventType, Category], int],
) -> None:
    """Raise on the first age-merge violation; warn on oversized field groups."""
    for row in rows:
        cats = set(_row_categories(row))
        total = sum(counts.get((row.event_type, c), 0) for c in cats)
        is_track = EventVenueMapping.get(row.event_type) == Venue.TRACK
        if not is_track and total > _TRACK_LANE_CAP:
            print(
                f"⚠️  Oversized field group {row.event_group_id}: {total} athletes "
                f"(soft cap {_TRACK_LANE_CAP})"
            )

    errors = age_merge_errors(rows, counts)
    if errors:
        raise ConstraintViolation(errors[0])


def age_merge_errors(
    rows: list[EventScheduleRow],
    counts: dict[tuple[EventType, Category], int],
) -> list[str]:
    """Return ALL age-merge violations across rows (non-raising, for batch checks).

    Age-merge rules apply to TRACK events only. Field events may merge across any age
    boundary (a row may combine any categories); their only soft limit is the >8
    oversize warning emitted by the caller.

    Track rules:
      - Rekrutt never shares a heat with a non-Rekrutt category.
      - 11-14 never shares a heat with 18-19/Senior/Masters (but 11-14 + 15-17 is OK).
      - combined athletes must fit the 8-lane heat cap.
      - hurdles: may mix distances and heights; each distinct (distance, height)
        setup costs a gutter lane, so the heat must fit `hurdle_lane_capacity`.
    """
    seniors = _EIGHTEEN_PLUS_SR | MASTERS_CATEGORIES

    out: list[str] = []
    for row in rows:
        cats = set(_row_categories(row))
        if not cats:
            continue
        if EventVenueMapping.get(row.event_type) != Venue.TRACK:
            continue  # field events: merge across any age boundary

        rekrutt = cats & _REKRUTT
        if rekrutt and (cats - _REKRUTT):
            out.append(
                f"Age merge violation in {row.event_group_id}: Rekrutt mixed with "
                f"older categories in a track heat ({_fmt(cats)})"
            )
            continue

        if (cats & _ELEVEN_FOURTEEN) and (cats & seniors):
            out.append(
                f"Age merge violation in {row.event_group_id}: 11-14 cannot share a "
                f"track heat with 18-19/Senior/Masters ({_fmt(cats)})"
            )
            continue

        total = sum(counts.get((row.event_type, c), 0) for c in cats)
        if is_hurdles_event(row.event_type):
            err = _hurdle_merge_error(row, list(cats), total)
            if err:
                out.append(err)
        elif total > _TRACK_LANE_CAP and len(cats) > 1:
            out.append(
                f"Track heat {row.event_group_id} has {total} athletes across "
                f"{len(cats)} categories, exceeding the {_TRACK_LANE_CAP}-lane cap"
            )
    return out


def _hurdle_merge_error(
    row: EventScheduleRow,
    cats: list[Category],
    total: int,
) -> str | None:
    """Return a hurdle merge violation message, or None if the row is valid.

    Hurdle categories may mix distances and heights. Each distinct (distance, height)
    setup needs a gutter lane between it and the next, so the heat must fit
    `hurdle_lane_capacity` (effective lanes - (distinct setups - 1)).
    """
    capacity = hurdle_lane_capacity(row.event_type, cats)
    if total > capacity:
        return (
            f"Hurdle heat {row.event_group_id} has {total} athletes but only "
            f"{capacity} usable lanes for these categories ({_fmt(set(cats))})"
        )
    return None


def _fmt(cats: set[Category]) -> str:
    return ', '.join(sorted(c.value for c in cats))


def validate_and_report(
    rows: list[EventScheduleRow],
    atom_events: list[Event],
    athletes: list[Athlete],
    *,
    slot_duration_minutes: int = 5,
) -> tuple[bool, list[str]]:
    """Validate and return (is_valid, error messages) instead of raising."""
    try:
        validate_event_schedule(
            rows,
            atom_events,
            athletes,
            slot_duration_minutes=slot_duration_minutes,
        )
        return (True, [])
    except ConstraintViolation as e:
        return (False, [str(e)])
