"""
Functional, stateless implementation of the track meet scheduler.

This module provides pure functions for creating Z3 scheduling constraints
and solving the track meet scheduling problem without any class-based state.
All data is passed explicitly as function arguments and returned as results.

See CONSTRAINTS.md for the scheduling rules and optimization goals.
"""

import time
from dataclasses import dataclass
from typing import Any

import z3  # type: ignore

from .models import (
    Athlete,
    EventGroup,
    EventType,
    EventVenueMapping,
    Venue,
    get_venue_for_event,
    is_young_category,
    is_youngest_category,
    get_category_age_order,
    get_track_event_order,
    is_hurdles_event,
    TRACK_DISTANCE_ORDER,
)
from .types import SchedulingResult


@dataclass(frozen=True)
class SchedulingConfig:
    """Configuration parameters for the scheduler."""

    total_personnel: int
    max_time_slots: int
    slot_duration_minutes: int = 5


@dataclass(frozen=True)
class SchedulingVariables:
    """Z3 variables used in the scheduling problem."""

    event_start_slot_vars: dict[str, dict[int, Any]]  # event_start[event][slot] = Bool
    event_active_vars: dict[str, dict[int, Any]]  # event_active[event][slot] = Bool
    slot_used_vars: dict[int, Any]  # slot_used[slot] = Bool
    total_slots: Any  # Z3 Int variable


@dataclass(frozen=True)
class SchedulingProblem:
    """Complete scheduling problem data."""

    events: dict[str, EventGroup]
    athletes: list[Athlete]
    config: SchedulingConfig
    event_duration_slots: dict[str, int]


@dataclass(frozen=True)
class SchedulingSolution:
    """Result of solving the scheduling problem."""

    status: str  # "solved", "unsolvable", "timeout"
    schedule: dict[int, list[dict[str, Any]]]
    total_slots: int
    total_duration_minutes: int
    slot_duration_minutes: int
    events_per_slot: dict[int, int]
    slots_with_events: int
    optimization_stats: dict[str, Any] | None = None


def build_athlete_event_groups(
    events: dict[str, EventGroup], athletes: list[Athlete]
) -> dict[str, list[str]]:
    """Map each athlete to their event group IDs.

    Returns a dict mapping athlete name to list of event group IDs they participate in.
    """
    # Build mapping from individual event ID to event group ID
    event_to_group: dict[str, str] = {}
    for group_id, group in events.items():
        for event in group.events:
            event_to_group[event.id] = group_id

    # Map each athlete to their event groups
    athlete_groups: dict[str, list[str]] = {}
    for athlete in athletes:
        group_ids: set[str] = set()
        for event in athlete.events:
            if event.id in event_to_group:
                group_ids.add(event_to_group[event.id])
        if group_ids:
            athlete_groups[athlete.name] = list(group_ids)

    return athlete_groups


def get_youngest_event_groups(events: dict[str, EventGroup]) -> set[str]:
    """Get event group IDs that contain 10 year olds (highest priority to finish early)."""
    youngest_groups: set[str] = set()
    for group_id, group in events.items():
        for event in group.events:
            if is_youngest_category(event.age_category):
                youngest_groups.add(group_id)
                break
    return youngest_groups


def get_young_event_groups(events: dict[str, EventGroup]) -> set[str]:
    """Get event group IDs that contain young athletes (10/11/12)."""
    young_groups: set[str] = set()
    for group_id, group in events.items():
        for event in group.events:
            if is_young_category(event.age_category):
                young_groups.add(group_id)
                break
    return young_groups


def get_older_athletes_with_multiple_events(
    events: dict[str, EventGroup], athletes: list[Athlete]
) -> dict[str, list[str]]:
    """Get older athletes (13+) who have multiple events.

    Returns dict mapping athlete name to list of event group IDs.
    Only includes athletes with 2+ events who are NOT in young categories.
    """
    athlete_groups = build_athlete_event_groups(events, athletes)

    # Build mapping from event group to categories it contains
    group_categories: dict[str, set[str]] = {}
    for group_id, group in events.items():
        group_categories[group_id] = {event.age_category for event in group.events}

    older_multi_event_athletes: dict[str, list[str]] = {}

    for athlete in athletes:
        if athlete.name not in athlete_groups:
            continue

        group_ids = athlete_groups[athlete.name]
        if len(group_ids) < 2:
            continue

        # Check if athlete is in young categories
        athlete_is_young = False
        for event in athlete.events:
            if is_young_category(event.age_category):
                athlete_is_young = True
                break

        if not athlete_is_young:
            older_multi_event_athletes[athlete.name] = group_ids

    return older_multi_event_athletes


def create_scheduling_problem(
    events: list[EventGroup], athletes: list[Athlete], config: SchedulingConfig
) -> SchedulingProblem:
    """Create a scheduling problem from input data."""
    events_dict = {e.id: e for e in events}

    # Calculate how many slots each event needs
    event_duration_slots = {}
    for event in events:
        slots_needed = (
            event.duration_minutes + config.slot_duration_minutes - 1
        ) // config.slot_duration_minutes
        event_duration_slots[event.id] = slots_needed

    return SchedulingProblem(
        events=events_dict,
        athletes=athletes,
        config=config,
        event_duration_slots=event_duration_slots,
    )


def create_z3_variables(problem: SchedulingProblem) -> SchedulingVariables:
    """Create Z3 variables for the scheduling problem."""
    event_start_slot_vars: dict[str, dict[int, Any]] = {}
    event_active_vars: dict[str, dict[int, Any]] = {}

    # Create boolean variables for each event and time slot
    for event_id in problem.events:
        event_start_slot_vars[event_id] = {}
        event_active_vars[event_id] = {}
        for slot in range(problem.config.max_time_slots):
            event_start_slot_vars[event_id][slot] = z3.Bool(
                f"start_{event_id}_s_{slot}"
            )
            event_active_vars[event_id][slot] = z3.Bool(f"active_{event_id}_s_{slot}")

    # Create slot usage variables
    slot_used_vars = {}
    for slot in range(problem.config.max_time_slots):
        slot_used_vars[slot] = z3.Bool(f"slot_{slot}")

    # Total slots variable
    total_slots = z3.Int("total_slots")

    return SchedulingVariables(
        event_start_slot_vars=event_start_slot_vars,
        event_active_vars=event_active_vars,
        slot_used_vars=slot_used_vars,
        total_slots=total_slots,
    )


def add_basic_constraints(
    solver: z3.Solver, problem: SchedulingProblem, variables: SchedulingVariables
) -> None:
    """Add fundamental constraints for multi-slot events."""
    # Bound total slots
    solver.add(variables.total_slots >= 1)
    solver.add(variables.total_slots <= problem.config.max_time_slots)

    # Each event must start in exactly one slot
    for event_id in problem.events:
        duration_slots = problem.event_duration_slots[event_id]
        valid_start_slots = list(
            range(problem.config.max_time_slots - duration_slots + 1)
        )

        if valid_start_slots:
            solver.add(
                z3.PbEq(
                    [
                        (variables.event_start_slot_vars[event_id][slot], 1)
                        for slot in valid_start_slots
                    ],
                    1,
                )
            )

            # Force invalid start slots to be False
            # This is critical for Sum expressions used in spacing constraints
            for slot in range(
                problem.config.max_time_slots - duration_slots + 1,
                problem.config.max_time_slots,
            ):
                solver.add(z3.Not(variables.event_start_slot_vars[event_id][slot]))

            # If event starts at slot s, it's active for duration_slots consecutive slots
            for start_slot in valid_start_slots:
                for active_slot in range(problem.config.max_time_slots):
                    if start_slot <= active_slot < start_slot + duration_slots:
                        # If event starts at start_slot, it must be active at active_slot
                        solver.add(
                            z3.Implies(
                                variables.event_start_slot_vars[event_id][start_slot],
                                variables.event_active_vars[event_id][active_slot],
                            )
                        )
                    else:
                        # If event starts at start_slot, it must NOT be active at active_slot
                        solver.add(
                            z3.Implies(
                                variables.event_start_slot_vars[event_id][start_slot],
                                z3.Not(
                                    variables.event_active_vars[event_id][active_slot]
                                ),
                            )
                        )

    # Link slot_used to event activity
    for slot in range(problem.config.max_time_slots):
        events_active_in_slot = [
            variables.event_active_vars[event_id][slot] for event_id in problem.events
        ]
        solver.add(variables.slot_used_vars[slot] == z3.Or(events_active_in_slot))

    # Total slots calculation: total_slots is the highest used slot + 1
    for slot in range(problem.config.max_time_slots):
        # If this slot is used, then total_slots must be at least slot + 1
        solver.add(
            z3.Implies(
                variables.slot_used_vars[slot], variables.total_slots >= slot + 1
            )
        )
        # If total_slots > slot, then this slot must be used (no gaps)
        solver.add(
            z3.Implies(variables.total_slots > slot, variables.slot_used_vars[slot])
        )

    # Symmetry breaking: force the first track event (by ordering rules) to start in slot 0
    # This must match the ordering used in track precedence constraints
    track_groups: list[EventGroup] = [
        group for group in problem.events.values()
        if group.event_type in TRACK_DISTANCE_ORDER
    ]

    if track_groups:
        # Sort with same ordering as precedence constraints (including flexible gender)
        sorted_groups = _sort_track_groups_for_spacing(track_groups, problem.athletes)
        first_track_event = sorted_groups[0].id
        solver.add(variables.event_start_slot_vars[first_track_event][0])


def _get_event_group_sort_key(group: EventGroup) -> tuple[int, int, int]:
    """Get sort key for an event group: (distance_order, is_hurdles, min_age).

    This ensures track events are ordered:
    1. By distance (shortest first)
    2. Non-hurdles before hurdles of same distance
    3. By age within each (youngest first)
    """
    distance_order = get_track_event_order(group.event_type)
    hurdles_order = 1 if is_hurdles_event(group.event_type) else 0
    min_age = min(get_category_age_order(e.age_category) for e in group.events)
    return (distance_order, hurdles_order, min_age)


def _sort_track_groups_for_spacing(
    track_groups: list[EventGroup],
    athletes: list[Athlete],
) -> list[EventGroup]:
    """Sort track groups with flexible gender ordering for better spacing.

    Base ordering: distance → hurdles → age (youngest first)

    Within each (distance, hurdles, age_tier), we may swap gender order
    to give multi-event athletes more spacing. The gender with more
    multi-event athletes goes later (more time from their field events).
    """
    if not track_groups:
        return []

    # Initial sort by base criteria
    sorted_groups = sorted(track_groups, key=_get_event_group_sort_key)

    # Build mapping: athlete -> their track groups
    athlete_track_groups: dict[str, set[str]] = {}
    for athlete in athletes:
        track_event_ids = {
            e.id for e in athlete.events
            if EventVenueMapping.get(e.event_type) == Venue.TRACK
        }
        for group in sorted_groups:
            for event in group.events:
                if event.id in track_event_ids:
                    if athlete.name not in athlete_track_groups:
                        athlete_track_groups[athlete.name] = set()
                    athlete_track_groups[athlete.name].add(group.id)

    # Count multi-event athletes per track group
    # (athletes who have both track and non-track events)
    multi_event_count: dict[str, int] = {g.id: 0 for g in sorted_groups}
    for athlete in athletes:
        has_track = any(EventVenueMapping.get(e.event_type) == Venue.TRACK for e in athlete.events)
        has_field = any(EventVenueMapping.get(e.event_type) != Venue.TRACK for e in athlete.events)
        if has_track and has_field:
            for group_id in athlete_track_groups.get(athlete.name, set()):
                multi_event_count[group_id] += 1

    # Find swappable pairs: same distance, hurdles, age tier, different gender
    # Age tiers: 10, 11-12, 13-14, 15+
    def get_age_tier(min_age: int) -> int:
        if min_age <= 10:
            return 0
        elif min_age <= 12:
            return 1
        elif min_age <= 14:
            return 2
        else:
            return 3

    def is_boys_group(group: EventGroup) -> bool:
        # Check if all events are boys/men categories
        return all(
            e.age_category.value.startswith("G") or e.age_category.value.startswith("Menn")
            for e in group.events
        )

    # Process consecutive pairs and swap if beneficial
    result = sorted_groups.copy()
    i = 0
    while i < len(result) - 1:
        g1, g2 = result[i], result[i + 1]

        # Check if they're swappable (same distance, hurdles, age tier, different gender)
        key1 = _get_event_group_sort_key(g1)
        key2 = _get_event_group_sort_key(g2)

        dist1, hurdles1, age1 = key1
        dist2, hurdles2, age2 = key2

        tier1 = get_age_tier(age1)
        tier2 = get_age_tier(age2)
        same_block = (dist1 == dist2 and hurdles1 == hurdles2 and tier1 == tier2)
        different_gender = is_boys_group(g1) != is_boys_group(g2)
        # Only swap for 15+ tier (tier 3) - younger athletes need to finish first
        is_15plus = tier1 == 3

        if same_block and different_gender and is_15plus:
            # Swap if g1 has MORE multi-event athletes (should go later)
            count1 = multi_event_count[g1.id]
            count2 = multi_event_count[g2.id]

            if count1 > count2:
                # Swap: put the one with more multi-event athletes later
                result[i], result[i + 1] = result[i + 1], result[i]

        i += 1

    return result


def add_track_precedence_constraints(
    solver: z3.Solver, problem: SchedulingProblem, variables: SchedulingVariables
) -> int:
    """Ensure track events run in strict order: distance → hurdles → age.

    Order rules:
    1. Shortest distance to longest (60m → 100m → 200m → ...)
    2. Non-hurdles before hurdles of same/similar distance
    3. Youngest to oldest within each distance/hurdles block
    4. Within same block, gender order is flexible for multi-event spacing
    """
    constraint_count = 0

    # Get all track event groups and sort them by the ordering rules
    track_groups: list[EventGroup] = [
        group for group in problem.events.values()
        if group.event_type in TRACK_DISTANCE_ORDER
    ]

    if not track_groups:
        print("  No track events to order")
        return 0

    # Sort with flexible gender ordering for better multi-event spacing
    sorted_groups = _sort_track_groups_for_spacing(track_groups, problem.athletes)

    print(f"  Track event ordering ({len(sorted_groups)} groups):")
    for i, group in enumerate(sorted_groups):
        min_age = min(get_category_age_order(e.age_category) for e in group.events)
        categories = "/".join(e.age_category.value for e in group.events)
        print(f"    {i+1}. {group.id} - {group.event_type.value} ({categories}) [age={min_age}]")

    # Add strict precedence: each group must start before the next one
    for i in range(len(sorted_groups) - 1):
        earlier_group = sorted_groups[i]
        later_group = sorted_groups[i + 1]

        earlier_id = earlier_group.id
        later_id = later_group.id

        # Verify these IDs exist in our variables
        if earlier_id not in variables.event_start_slot_vars:
            print(f"    WARNING: {earlier_id} not found in event_start_slot_vars!")
            continue
        if later_id not in variables.event_start_slot_vars:
            print(f"    WARNING: {later_id} not found in event_start_slot_vars!")
            continue

        # Calculate start times using Z3 expressions
        earlier_start = z3.Sum([
            z3.If(variables.event_start_slot_vars[earlier_id][slot], slot, 0)
            for slot in range(problem.config.max_time_slots)
        ])
        later_start = z3.Sum([
            z3.If(variables.event_start_slot_vars[later_id][slot], slot, 0)
            for slot in range(problem.config.max_time_slots)
        ])

        # Later event must start strictly after earlier event starts
        solver.add(later_start > earlier_start)
        constraint_count += 1
        print(f"    Constraint: {later_id} > {earlier_id}")

    print(f"  Total track precedence constraints added: {constraint_count}")
    print()

    return constraint_count


def add_athlete_conflict_constraints(
    solver: z3.Solver, problem: SchedulingProblem, variables: SchedulingVariables
) -> int:
    """Prevent athletes from competing simultaneously."""
    constraint_count = 0

    # Create a mapping from individual event IDs to event group IDs
    event_to_group: dict[str, str] = {}
    for group_id, group in problem.events.items():
        for event in group.events:
            event_to_group[event.id] = group_id

    # Group athletes by their event group combinations to avoid duplicate constraints
    group_combinations: dict[frozenset[str], list[str]] = {}

    for athlete in problem.athletes:
        if len(athlete.events) > 1:
            # Get event group IDs for this athlete (only those in the problem)
            athlete_group_ids = frozenset(
                event_to_group[event.id]
                for event in athlete.events
                if event.id in event_to_group
            )

            if len(athlete_group_ids) > 1:  # Only if multiple groups after filtering
                if athlete_group_ids not in group_combinations:
                    group_combinations[athlete_group_ids] = []
                group_combinations[athlete_group_ids].append(athlete.name)

    print(
        f"  Found {len(group_combinations)} unique event group combinations among {len(problem.athletes)} athletes"
    )

    # Add constraints for each unique event group combination
    for group_ids, athlete_names in group_combinations.items():
        group_ids_list = list(group_ids)
        print(
            f"    Event groups {group_ids_list} shared by {len(athlete_names)} athletes: {athlete_names[:3]}{'...' if len(athlete_names) > 3 else ''}"
        )

        for slot in range(problem.config.max_time_slots):
            # At most one of these event groups can be active per slot
            groups_active_in_slot = [
                variables.event_active_vars[group_id][slot]
                for group_id in group_ids_list
            ]

            solver.add(z3.PbLe([(var, 1) for var in groups_active_in_slot], 1))
            constraint_count += 1

    print(f"  Total athlete conflict constraints added: {constraint_count}")
    return constraint_count


def add_venue_conflict_constraints(
    solver: z3.Solver, problem: SchedulingProblem, variables: SchedulingVariables
) -> int:
    """Ensure only one event per venue per slot."""
    # Group events by venue
    venue_events: dict[Venue, list[str]] = {}
    for event_group in problem.events.values():
        # For EventGroup, use category from first event (all events in group share age tier)
        first_event = event_group.events[0] if event_group.events else None
        category = first_event.age_category if first_event else None
        venue = get_venue_for_event(event_group.event_type, category)
        if venue is not None:
            if venue not in venue_events:
                venue_events[venue] = []
            venue_events[venue].append(event_group.id)

    constraint_count = 0

    # For each venue, ensure at most one event active per slot
    for venue, event_ids in venue_events.items():
        if (
            len(event_ids) > 1
        ):  # Only add constraints if there are multiple events for this venue
            for slot in range(problem.config.max_time_slots):
                venue_vars_active_in_slot = [
                    variables.event_active_vars[event_id][slot]
                    for event_id in event_ids
                ]
                solver.add(z3.PbLe([(var, 1) for var in venue_vars_active_in_slot], 1))
                constraint_count += 1

    return constraint_count


def _needs_extra_spacing(earlier_type: EventType, later_type: EventType) -> bool:
    """Check if transition between two track event types needs extra spacing.

    Extra spacing (2 slots / 10 min) is needed when:
    - Switching to a different starting position on the track
    - Switching to hurdles (need time to set up)

    Starting positions (clockwise from finish):
    - Block 0: 60m, 60m_hurdles, 80m_hurdles (near finish)
    - Block 1: 100m, 100m_hurdles (near finish)
    - Block 2: 1500m (+100m mark)
    - Block 3: 200m, 5000m (+200m mark)
    - Block 4: 400m (further around curve)
    - Block 5: 800m (even further)
    """
    # Switching to hurdles always needs extra time
    if is_hurdles_event(later_type) and not is_hurdles_event(earlier_type):
        return True

    # Get the base distance order for both events
    earlier_order = get_track_event_order(earlier_type)
    later_order = get_track_event_order(later_type)

    # Define distance blocks by their indices in TRACK_DISTANCE_ORDER:
    # 0: m60, 1: m60_hurdles, 2: m80_hurdles, 3: m100, 4: m100_hurdles,
    # 5: m200, 6: m1500, 7: m5000, 8: m400, 9: m800
    distance_blocks = [
        (0, 2),   # 60m block (60m, 60m_hurdles, 80m_hurdles)
        (3, 4),   # 100m block (100m, 100m_hurdles)
        (5, 7),   # 200m/1500m/5000m block (all around +200m mark)
        (8, 8),   # 400m
        (9, 9),   # 800m
    ]

    def get_block(order: int) -> int:
        for i, (start, end) in enumerate(distance_blocks):
            if start <= order <= end:
                return i
        return -1

    earlier_block = get_block(earlier_order)
    later_block = get_block(later_order)

    # Different blocks = switching position = extra spacing
    return earlier_block != later_block


def _is_young_track_group(group: EventGroup) -> bool:
    """Check if all athletes in a track event group are young (≤12)."""
    return all(is_young_category(e.age_category) for e in group.events)


def add_track_spacing_constraints(
    solver: z3.Solver, problem: SchedulingProblem, variables: SchedulingVariables
) -> int:
    """Ensure proper spacing between consecutive track events.

    See CONSTRAINTS.md for spacing rules.
    """
    constraint_count = 0

    # Get all track event groups sorted by the ordering rules
    track_groups: list[EventGroup] = [
        group for group in problem.events.values()
        if group.event_type in TRACK_DISTANCE_ORDER
    ]

    if len(track_groups) < 2:
        print("  Less than 2 track events, no spacing constraints needed")
        return 0

    # Sort by the same ordering as precedence (including flexible gender swap)
    sorted_groups = _sort_track_groups_for_spacing(track_groups, problem.athletes)

    print(f"  Adding track spacing constraints ({len(sorted_groups)} groups):")

    # Add spacing between consecutive track events
    for i in range(len(sorted_groups) - 1):
        earlier_group = sorted_groups[i]
        later_group = sorted_groups[i + 1]

        earlier_id = earlier_group.id
        later_id = later_group.id
        earlier_duration = problem.event_duration_slots[earlier_id]

        # Determine gap size based on event types and athlete ages
        needs_extra = _needs_extra_spacing(earlier_group.event_type, later_group.event_type)

        if needs_extra:
            # Switching position or to hurdles - always need 2 slots
            min_gap = 2
            gap_reason = "position/hurdles change"
        elif _is_young_track_group(earlier_group) and _is_young_track_group(later_group):
            # Both groups are young athletes - can run back-to-back
            min_gap = 0
            gap_reason = "young athletes, back-to-back OK"
        else:
            # At least one group has older athletes (13+) - need standard gap
            min_gap = 1
            gap_reason = "older athletes need prep time"

        # Calculate start times using Z3 expressions
        earlier_start = z3.Sum([
            z3.If(variables.event_start_slot_vars[earlier_id][slot], slot, 0)
            for slot in range(problem.config.max_time_slots)
        ])
        later_start = z3.Sum([
            z3.If(variables.event_start_slot_vars[later_id][slot], slot, 0)
            for slot in range(problem.config.max_time_slots)
        ])

        # later_start >= earlier_start + earlier_duration + min_gap
        solver.add(later_start >= earlier_start + earlier_duration + min_gap)
        constraint_count += 1

        print(f"    {earlier_group.event_type.value} → {later_group.event_type.value}: {min_gap} slot gap ({gap_reason})")

    print(f"  Total track spacing constraints added: {constraint_count}")
    print()

    return constraint_count


def add_youngest_athlete_finish_constraint(
    solver: z3.Solver,
    problem: SchedulingProblem,
    variables: SchedulingVariables,
    max_finish_slot: int,
) -> int:
    """Add constraints that 10 year old events must finish by a given slot.

    10 year olds have HIGHEST priority to finish early.
    """
    youngest_groups = get_youngest_event_groups(problem.events)

    if not youngest_groups:
        print("  No 10 year old event groups found")
        return 0

    constraint_count = 0
    print(f"  Found {len(youngest_groups)} 10-year-old event groups")

    for group_id in youngest_groups:
        duration_slots = problem.event_duration_slots[group_id]
        max_start = max_finish_slot - duration_slots + 1

        if max_start < 0:
            print(f"    WARNING: {group_id} cannot fit before slot {max_finish_slot}")
            continue

        for slot in range(max_start + 1, problem.config.max_time_slots):
            solver.add(z3.Not(variables.event_start_slot_vars[group_id][slot]))
            constraint_count += 1

        print(f"    {group_id}: must finish by slot {max_finish_slot}")

    print(f"  Total 10-year-old constraints added: {constraint_count}")
    return constraint_count


def add_young_athlete_finish_constraint(
    solver: z3.Solver,
    problem: SchedulingProblem,
    variables: SchedulingVariables,
    max_finish_slot: int,
) -> int:
    """Add constraints that young athlete events (11/12) must finish by a given slot.

    This is for 11/12 year olds (10 year olds have separate, tighter constraint).
    """
    young_groups = get_young_event_groups(problem.events)
    youngest_groups = get_youngest_event_groups(problem.events)
    # Only constrain 11/12 year olds here (10s handled separately)
    young_only_groups = young_groups - youngest_groups

    if not young_only_groups:
        print("  No 11/12 year old event groups found")
        return 0

    constraint_count = 0
    print(f"  Found {len(young_only_groups)} 11/12-year-old event groups")

    for group_id in young_only_groups:
        duration_slots = problem.event_duration_slots[group_id]
        max_start = max_finish_slot - duration_slots + 1

        if max_start < 0:
            print(f"    WARNING: {group_id} cannot fit before slot {max_finish_slot}")
            continue

        for slot in range(max_start + 1, problem.config.max_time_slots):
            solver.add(z3.Not(variables.event_start_slot_vars[group_id][slot]))
            constraint_count += 1

        print(f"    {group_id}: must finish by slot {max_finish_slot}")

    print(f"  Total 11/12-year-old constraints added: {constraint_count}")
    return constraint_count


def add_track_finish_constraint(
    solver: z3.Solver,
    problem: SchedulingProblem,
    variables: SchedulingVariables,
    max_finish_slot: int,
) -> int:
    """Add constraints that all track events must finish by a given slot.

    This allows track events to end earlier than field events, which is
    common when track officials need to leave earlier than field officials.
    """
    track_groups = [
        group for group in problem.events.values()
        if group.event_type in TRACK_DISTANCE_ORDER
    ]

    if not track_groups:
        print("  No track event groups found")
        return 0

    constraint_count = 0
    print(f"  Found {len(track_groups)} track event groups")

    for group in track_groups:
        group_id = group.id
        duration_slots = problem.event_duration_slots[group_id]
        max_start = max_finish_slot - duration_slots + 1

        if max_start < 0:
            print(f"    WARNING: {group_id} cannot fit before slot {max_finish_slot}")
            continue

        for slot in range(max_start + 1, problem.config.max_time_slots):
            solver.add(z3.Not(variables.event_start_slot_vars[group_id][slot]))
            constraint_count += 1

        print(f"    {group_id}: must finish by slot {max_finish_slot}")

    print(f"  Total track finish constraints added: {constraint_count}")
    return constraint_count


def add_older_athlete_spacing_constraints(
    solver: z3.Solver,
    problem: SchedulingProblem,
    variables: SchedulingVariables,
    min_gap_slots: int,
) -> int:
    """Add recovery gap constraints for older athletes (13+) with multiple events.

    See CONSTRAINTS.md for the merging vs spacing conflict.
    """
    older_athletes = get_older_athletes_with_multiple_events(problem.events, problem.athletes)

    if not older_athletes:
        print("  No older athletes with multiple events found")
        return 0

    constraint_count = 0
    print(f"  Found {len(older_athletes)} older athletes with multiple events")

    for athlete_name, group_ids in older_athletes.items():
        if len(group_ids) < 2:
            continue

        # For each pair of event groups this athlete participates in,
        # ensure minimum gap between them
        for i, group_id_1 in enumerate(group_ids):
            for group_id_2 in group_ids[i + 1 :]:
                duration_1 = problem.event_duration_slots[group_id_1]
                duration_2 = problem.event_duration_slots[group_id_2]

                # Calculate start times as Z3 expressions
                start_1 = z3.Sum(
                    [
                        z3.If(variables.event_start_slot_vars[group_id_1][slot], slot, 0)
                        for slot in range(problem.config.max_time_slots)
                    ]
                )
                start_2 = z3.Sum(
                    [
                        z3.If(variables.event_start_slot_vars[group_id_2][slot], slot, 0)
                        for slot in range(problem.config.max_time_slots)
                    ]
                )

                # Either event 1 ends min_gap_slots before event 2 starts,
                # or event 2 ends min_gap_slots before event 1 starts
                # end_1 = start_1 + duration_1 - 1, so gap starts at start_1 + duration_1
                # start_2 >= start_1 + duration_1 + min_gap_slots OR
                # start_1 >= start_2 + duration_2 + min_gap_slots

                solver.add(
                    z3.Or(
                        start_2 >= start_1 + duration_1 + min_gap_slots,
                        start_1 >= start_2 + duration_2 + min_gap_slots,
                    )
                )
                constraint_count += 1

        print(f"    {athlete_name}: {len(group_ids)} events with {min_gap_slots} slot gap")

    print(f"  Total older athlete spacing constraints added: {constraint_count}")
    return constraint_count


def verify_track_precedence_in_solution(
    solution: SchedulingSolution, athletes: list[Athlete]
) -> None:
    """Debug function to verify track precedence constraints are satisfied in the solution.

    Verifies the strict ordering: distance → hurdles → age
    (with flexible gender ordering for multi-event spacing in 15+ tier)
    """
    # Extract all track event groups and their start slots
    track_events_with_slots: list[tuple[str, int, EventGroup]] = []

    for slot, slot_events in solution.schedule.items():
        for event_info in slot_events:
            if event_info["is_start"]:
                event_group = event_info["event"]
                if event_group.event_type in TRACK_DISTANCE_ORDER:
                    track_events_with_slots.append((event_info["id"], slot, event_group))

    if not track_events_with_slots:
        print("🔍 No track events to verify")
        return

    # Extract just the groups for sorting
    track_groups = [item[2] for item in track_events_with_slots]
    # Sort using the same function as constraints (includes flexible gender swap)
    sorted_groups = _sort_track_groups_for_spacing(track_groups, athletes)

    # Build slot lookup for each group
    group_to_slot = {item[2].id: item[1] for item in track_events_with_slots}

    # Rebuild expected order with slots
    expected_order = [(g.id, group_to_slot[g.id], g) for g in sorted_groups]

    # Check that actual start slots match expected order
    print("🔍 Verifying track precedence (distance → hurdles → age):")
    violations: list[str] = []

    for i in range(len(expected_order) - 1):
        _, earlier_slot, earlier_group = expected_order[i]
        _, later_slot, later_group = expected_order[i + 1]

        earlier_cats = "/".join(e.age_category.value for e in earlier_group.events)
        later_cats = "/".join(e.age_category.value for e in later_group.events)

        if earlier_slot >= later_slot:
            violation_msg = f"❌ {earlier_group.event_type.value} ({earlier_cats}) slot {earlier_slot} should be < {later_group.event_type.value} ({later_cats}) slot {later_slot}"
            print(f"  {violation_msg}")
            violations.append(violation_msg)
        else:
            print(f"  ✅ {earlier_group.event_type.value} ({earlier_cats}) slot {earlier_slot} < {later_group.event_type.value} ({later_cats}) slot {later_slot}")

    if not violations:
        print("  🎉 All track precedence constraints satisfied!")
    else:
        print(f"  💥 Found {len(violations)} track precedence violations!")

    print()


def debug_event_durations(problem: SchedulingProblem) -> None:
    """Debug function to print event duration calculations."""
    print("Event duration calculations:")
    for event_id, event in problem.events.items():
        slots_needed = problem.event_duration_slots[event_id]
        print(
            f"  {event_id}: {event.duration_minutes} min -> {slots_needed} slots ({slots_needed * problem.config.slot_duration_minutes} min)"
        )
        max_start_slot = problem.config.max_time_slots - slots_needed
        print(
            f"    Can start in slots: 0-{max_start_slot} (max_time_slots={problem.config.max_time_slots})"
        )
    print()


def extract_solution(
    model: z3.ModelRef, problem: SchedulingProblem, variables: SchedulingVariables
) -> SchedulingSolution:
    """Extract solution from Z3 model."""
    schedule: dict[int, list[dict[str, Any]]] = {}

    for event_id in problem.events:
        for start_slot in range(problem.config.max_time_slots):
            if z3.is_true(
                model.eval(variables.event_start_slot_vars[event_id][start_slot])
            ):
                duration_slots = problem.event_duration_slots[event_id]

                # Add event to all slots it occupies
                for active_slot in range(start_slot, start_slot + duration_slots):
                    if active_slot not in schedule:
                        schedule[active_slot] = []
                    schedule[active_slot].append(
                        {
                            "event": problem.events[event_id],
                            "id": event_id,
                            "start_slot": start_slot,
                            "duration_slots": duration_slots,
                            "is_start": active_slot == start_slot,
                            "slot_offset": active_slot - start_slot,
                        }
                    )
                break

    # Calculate statistics
    if schedule:
        max_slot_used = max(schedule.keys())
        total_slots = max_slot_used + 1
        total_duration = total_slots * problem.config.slot_duration_minutes
    else:
        total_slots = 0
        total_duration = 0

    return SchedulingSolution(
        status="solved",
        schedule=schedule,
        total_slots=total_slots,
        total_duration_minutes=total_duration,
        slot_duration_minutes=problem.config.slot_duration_minutes,
        events_per_slot={slot: len(events) for slot, events in schedule.items()},
        slots_with_events=len(schedule),
    )


def solve_scheduling_problem(
    problem: SchedulingProblem,
    timeout_ms: int = 30000,
    max_slots: int | None = None,
    youngest_finish_slot: int | None = None,
    young_finish_slot: int | None = None,
    older_min_gap_slots: int = 0,
    track_finish_slot: int | None = None,
) -> SchedulingSolution:
    """Solve the scheduling problem with timeout, optional slot limit, and spacing constraints.

    Args:
        problem: Scheduling problem data
        timeout_ms: Timeout in milliseconds
        max_slots: Maximum slots allowed (defaults to problem.config.max_time_slots)
        youngest_finish_slot: If set, 10 year olds must finish by this slot (highest priority)
        young_finish_slot: If set, 11/12 year olds must finish by this slot
        older_min_gap_slots: Minimum gap in slots between events for older athletes (13+)
        track_finish_slot: If set, all track events must finish by this slot
    """
    # Use the problem's max_time_slots if no specific limit is provided
    if max_slots is None:
        max_slots = problem.config.max_time_slots

    # Create solver and variables
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    variables = create_z3_variables(problem)

    # Debug: print event duration calculations (only for initial solve)
    if max_slots == problem.config.max_time_slots:
        debug_event_durations(problem)

    # Add all constraints in the correct order
    verbose = (
        max_slots == problem.config.max_time_slots
    )  # Only verbose for initial solve
    add_all_constraints(
        solver, problem, variables,
        verbose=verbose,
        youngest_finish_slot=youngest_finish_slot,
        young_finish_slot=young_finish_slot,
        older_min_gap_slots=older_min_gap_slots,
        track_finish_slot=track_finish_slot,
    )

    # Add the slot limit constraint
    solver.add(variables.total_slots <= max_slots)

    # Solve the problem
    if verbose:
        print("Finding feasible solution...")
    result = solver.check()

    if result == z3.sat:
        if verbose:
            print("✅ Feasible solution found!")
        model = solver.model()
        solution = extract_solution(model, problem, variables)
        return solution
    elif result == z3.unknown:
        if verbose:
            print("⏰ Timeout - no solution found within time limit")
        return SchedulingSolution(
            "timeout", {}, 0, 0, problem.config.slot_duration_minutes, {}, 0
        )
    else:
        if verbose:
            print("❌ No solution exists")
        return SchedulingSolution(
            "unsolvable", {}, 0, 0, problem.config.slot_duration_minutes, {}, 0
        )


def solve_with_optimization(
    problem: SchedulingProblem,
    timeout_ms: int = 10000,
    optimization_timeout_ms: int = 10000,  # noqa: ARG001 - reserved for future use
    print_schedules: bool = True,
    track_finish_slot: int | None = None,
) -> SchedulingSolution:
    """Four-phase solving with age-based spacing optimization.

    Phase 1: Find minimum slots (compact schedule)
    Phase 2a: Binary search for 10 year old finish slot (highest priority)
    Phase 2b: Binary search for 11/12 year old finish slot
    Phase 3: Binary search for older athlete min gap (maximize recovery time)

    Args:
        track_finish_slot: If set, all track events must finish by this slot
    """
    total_start_time = time.time()

    # Identify athlete groups by age
    youngest_groups = get_youngest_event_groups(problem.events)
    young_groups = get_young_event_groups(problem.events)
    young_only_groups = young_groups - youngest_groups  # 11/12 only
    older_athletes = get_older_athletes_with_multiple_events(problem.events, problem.athletes)

    print(f"📊 Age-based scheduling info:")
    print(f"   10-year-old event groups: {len(youngest_groups)}")
    print(f"   11/12-year-old event groups: {len(young_only_groups)}")
    print(f"   Older athletes with multiple events (13+): {len(older_athletes)}")

    # Phase 1: Find minimum slots without spacing constraints
    print("\n🚀 Phase 1: Finding minimum slot count...")
    phase1_start = time.time()

    initial_solution = solve_scheduling_problem(
        problem, timeout_ms, track_finish_slot=track_finish_slot
    )
    if initial_solution.status != "solved":
        print(f"❌ Phase 1 failed: {initial_solution.status}")
        return initial_solution

    initial_slots = initial_solution.total_slots
    phase1_time = time.time() - phase1_start
    print(f"✅ Phase 1 complete in {phase1_time:.2f}s: {initial_slots} slots")

    # Binary search to minimize slots
    best_slots = initial_slots
    low, high = 1, initial_slots - 1
    while low <= high:
        mid = (low + high) // 2
        solution = solve_scheduling_problem(
            problem, timeout_ms, max_slots=mid, track_finish_slot=track_finish_slot
        )
        if solution.status == "solved":
            best_slots = mid
            high = mid - 1
        else:
            low = mid + 1

    print(f"   Minimum slots: {best_slots}")

    # Phase 2a: Find optimal 10-year-old finish slot (highest priority)
    print(f"\n👶 Phase 2a: Optimizing 10-year-old finish time...")
    phase2a_start = time.time()

    best_youngest_finish = best_slots  # Default: no constraint
    if youngest_groups:
        youngest_durations = [problem.event_duration_slots[gid] for gid in youngest_groups]
        min_youngest_finish = max(youngest_durations) - 1

        low, high = min_youngest_finish, best_slots - 1
        while low <= high:
            mid = (low + high) // 2
            solution = solve_scheduling_problem(
                problem, timeout_ms,
                max_slots=best_slots,
                youngest_finish_slot=mid,
                track_finish_slot=track_finish_slot,
            )
            if solution.status == "solved":
                best_youngest_finish = mid
                high = mid - 1
            else:
                low = mid + 1

        print(f"   10-year-olds finish by slot {best_youngest_finish} ({best_youngest_finish * problem.config.slot_duration_minutes} min)")
    else:
        print("   No 10-year-old events to optimize")

    phase2a_time = time.time() - phase2a_start

    # Phase 2b: Find optimal 11/12-year-old finish slot
    print(f"\n🧒 Phase 2b: Optimizing 11/12-year-old finish time...")
    phase2b_start = time.time()

    best_young_finish = best_slots  # Default: no constraint
    if young_only_groups:
        young_durations = [problem.event_duration_slots[gid] for gid in young_only_groups]
        min_young_finish = max(young_durations) - 1

        low, high = min_young_finish, best_slots - 1
        while low <= high:
            mid = (low + high) // 2
            solution = solve_scheduling_problem(
                problem, timeout_ms,
                max_slots=best_slots,
                youngest_finish_slot=best_youngest_finish if youngest_groups else None,
                young_finish_slot=mid,
                track_finish_slot=track_finish_slot,
            )
            if solution.status == "solved":
                best_young_finish = mid
                high = mid - 1
            else:
                low = mid + 1

        print(f"   11/12-year-olds finish by slot {best_young_finish} ({best_young_finish * problem.config.slot_duration_minutes} min)")
    else:
        print("   No 11/12-year-old events to optimize")

    phase2b_time = time.time() - phase2b_start
    phase2_time = phase2a_time + phase2b_time

    # Phase 3: Maximize older athlete recovery gaps
    # Use the full time budget (max_time_slots) to allow spreading events for better recovery
    print(f"\n🏃 Phase 3: Maximizing older athlete recovery gaps...")
    print(f"   Time budget: {problem.config.max_time_slots} slots ({problem.config.max_time_slots * problem.config.slot_duration_minutes} min)")
    print(f"   Minimum needed: {best_slots} slots ({best_slots * problem.config.slot_duration_minutes} min)")
    phase3_start = time.time()

    best_gap = 0
    # Get baseline solution with young athlete constraints (no gap constraint yet)
    best_solution = solve_scheduling_problem(
        problem, timeout_ms,
        max_slots=problem.config.max_time_slots,  # Allow full time budget
        youngest_finish_slot=best_youngest_finish if youngest_groups else None,
        young_finish_slot=best_young_finish if young_only_groups else None,
        track_finish_slot=track_finish_slot,
    )
    if older_athletes:
        # Binary search for maximum feasible gap within time budget
        # Max gap is limited by available slots: if we have 24 slots and minimum is 20,
        # we have 4 extra slots that could be used for gaps
        available_extra_slots = problem.config.max_time_slots - best_slots
        # Each gap between events requires 1 slot, and athletes may have 2-4 events
        # A reasonable upper bound is the extra slots + some baseline
        max_possible_gap = min(
            (available_extra_slots + best_slots) // 3,  # Rough estimate
            problem.config.max_time_slots // 4,  # Don't go crazy
        )
        max_possible_gap = max(max_possible_gap, best_slots // 2)  # At least try half the slots

        low, high = 1, max_possible_gap

        while low <= high:
            mid = (low + high) // 2
            solution = solve_scheduling_problem(
                problem, timeout_ms,
                max_slots=problem.config.max_time_slots,  # Allow full time budget
                youngest_finish_slot=best_youngest_finish if youngest_groups else None,
                young_finish_slot=best_young_finish if young_only_groups else None,
                older_min_gap_slots=mid,
                track_finish_slot=track_finish_slot,
            )
            if solution.status == "solved":
                best_gap = mid
                best_solution = solution
                low = mid + 1  # Try larger gap
            else:
                high = mid - 1  # Need smaller gap

        print(f"   Older athlete minimum gap: {best_gap} slots ({best_gap * problem.config.slot_duration_minutes} min)")
    else:
        print("   No older athletes with multiple events to optimize")

    phase3_time = time.time() - phase3_start
    total_time = time.time() - total_start_time

    # Print final schedule
    if print_schedules and best_solution.status == "solved":
        from .schedule_printer import print_schedule
        events_list = list(problem.events.values())
        solution_result = _solution_to_result(best_solution, events_list, problem.athletes)
        print_schedule(result=solution_result, title="Final Optimized Schedule")

    print(f"\n🎉 Optimization complete!")
    print(f"   Total slots: {best_solution.total_slots}")
    print(f"   10-year-olds finish by: slot {best_youngest_finish} ({best_youngest_finish * problem.config.slot_duration_minutes} min)")
    print(f"   11/12-year-olds finish by: slot {best_young_finish} ({best_young_finish * problem.config.slot_duration_minutes} min)")
    print(f"   Older athlete min gap: {best_gap} slots ({best_gap * problem.config.slot_duration_minutes} min)")
    print(f"   ⏱️  Time: {total_time:.2f}s (P1: {phase1_time:.2f}s, P2: {phase2_time:.2f}s, P3: {phase3_time:.2f}s)")

    # Add optimization metadata to solution
    optimization_stats: dict[str, Any] = {
        "initial_slots": initial_slots,
        "final_slots": best_solution.total_slots,
        "youngest_finish_slot": best_youngest_finish,
        "young_finish_slot": best_young_finish,
        "older_min_gap_slots": best_gap,
        "track_finish_slot": track_finish_slot,
        "phase1_time": phase1_time,
        "phase2_time": phase2_time,
        "phase3_time": phase3_time,
        "total_time": total_time,
    }

    return SchedulingSolution(
        status=best_solution.status,
        schedule=best_solution.schedule,
        total_slots=best_solution.total_slots,
        total_duration_minutes=best_solution.total_duration_minutes,
        slot_duration_minutes=best_solution.slot_duration_minutes,
        events_per_slot=best_solution.events_per_slot,
        slots_with_events=best_solution.slots_with_events,
        optimization_stats=optimization_stats,
    )


# Convenience function to maintain API compatibility
def schedule_track_meet(
    events: list[EventGroup],
    athletes: list[Athlete],
    total_personnel: int,
    max_time_slots: int,
    timeout_ms: int = 10000,
    optimization_timeout_ms: int = 10000,
    print_schedules: bool = False,
    max_track_duration: int | None = None,
) -> SchedulingResult:
    """
    Main entry point for scheduling a track meet.

    Args:
        max_track_duration: If set, track events must finish within this many minutes

    Returns a SchedulingResult dataclass containing events, athletes, and solution.
    """
    config = SchedulingConfig(
        total_personnel=total_personnel, max_time_slots=max_time_slots
    )

    problem = create_scheduling_problem(events, athletes, config)

    # Convert max_track_duration (minutes) to slots
    track_finish_slot: int | None = None
    if max_track_duration is not None:
        track_finish_slot = max_track_duration // problem.config.slot_duration_minutes
        print(f"🏃 Track finish constraint: {max_track_duration} min = slot {track_finish_slot}")

    solution = solve_with_optimization(
        problem, timeout_ms, optimization_timeout_ms, print_schedules,
        track_finish_slot=track_finish_slot,
    )

    # Verify track precedence constraints in the solution
    if solution.status == "solved":
        verify_track_precedence_in_solution(solution, athletes)

    # Convert to SchedulingResult dataclass
    return SchedulingResult(
        status=solution.status,
        schedule=solution.schedule,
        total_slots=solution.total_slots,
        total_duration_minutes=solution.total_duration_minutes,
        slot_duration_minutes=solution.slot_duration_minutes,
        events_per_slot=solution.events_per_slot,
        slots_with_events=solution.slots_with_events,
        optimization_stats=solution.optimization_stats,
        events=events,
        athletes=athletes,
    )


def _solution_to_result(
    solution: SchedulingSolution, events: list[EventGroup], athletes: list[Athlete]
) -> SchedulingResult:
    """Convert a SchedulingSolution to SchedulingResult for use in print functions."""
    return SchedulingResult(
        status=solution.status,
        schedule=solution.schedule,
        total_slots=solution.total_slots,
        total_duration_minutes=solution.total_duration_minutes,
        slot_duration_minutes=solution.slot_duration_minutes,
        events_per_slot=solution.events_per_slot,
        slots_with_events=solution.slots_with_events,
        optimization_stats=solution.optimization_stats,
        events=events,
        athletes=athletes,
    )


def add_all_constraints(
    solver: z3.Solver,
    problem: SchedulingProblem,
    variables: SchedulingVariables,
    verbose: bool = True,
    youngest_finish_slot: int | None = None,
    young_finish_slot: int | None = None,
    older_min_gap_slots: int = 0,
    track_finish_slot: int | None = None,
) -> None:
    """Add all constraints to the solver in the correct order.

    Args:
        solver: Z3 solver instance
        problem: Scheduling problem data
        variables: Z3 variables
        verbose: Whether to print progress
        youngest_finish_slot: If set, 10 year olds must finish by this slot (highest priority)
        young_finish_slot: If set, 11/12 year olds must finish by this slot
        older_min_gap_slots: Minimum gap in slots between events for older athletes (13+)
        track_finish_slot: If set, all track events must finish by this slot
    """
    if verbose:
        print("Adding track precedence constraints...")
    add_track_precedence_constraints(solver, problem, variables)

    if verbose:
        print("Adding track spacing constraints...")
    add_track_spacing_constraints(solver, problem, variables)

    if verbose:
        print("Adding basic constraints...")
    add_basic_constraints(solver, problem, variables)

    if verbose:
        print("Adding athlete conflicts...")
    add_athlete_conflict_constraints(solver, problem, variables)

    if verbose:
        print("Adding venue conflicts...")
    add_venue_conflict_constraints(solver, problem, variables)

    # Add age-based spacing constraints (10 year olds first - highest priority)
    if youngest_finish_slot is not None:
        if verbose:
            print(f"Adding 10-year-old constraints (finish by slot {youngest_finish_slot})...")
        add_youngest_athlete_finish_constraint(solver, problem, variables, youngest_finish_slot)

    if young_finish_slot is not None:
        if verbose:
            print(f"Adding 11/12-year-old constraints (finish by slot {young_finish_slot})...")
        add_young_athlete_finish_constraint(solver, problem, variables, young_finish_slot)

    if older_min_gap_slots > 0:
        if verbose:
            print(f"Adding older athlete spacing constraints (min gap: {older_min_gap_slots} slots)...")
        add_older_athlete_spacing_constraints(solver, problem, variables, older_min_gap_slots)

    if track_finish_slot is not None:
        if verbose:
            print(f"Adding track finish constraints (finish by slot {track_finish_slot})...")
        add_track_finish_constraint(solver, problem, variables, track_finish_slot)
