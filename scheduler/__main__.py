import time

from .functional_scheduler import SchedulingResult, schedule_track_meet
from .html_schedule_generator import save_html_schedule
from .isonen_parser import parse_isonen_csv
from .models import (
    Athlete, Event, EventGroup, EventType, EventVenueMapping, Venue,
    get_hurdle_spec, hurdle_lane_capacity, is_hurdles_event,
)


def print_full_schedule(solution: SchedulingResult, title: str = "Full Schedule"):
    """Print all time slots in the schedule"""
    if solution.status != "solved":
        print(f"❌ Status: {solution.status}")
        return

    print(f"\n📅 {title}")
    print(f"Total time slots used: {solution.total_slots}")
    print(f"Total duration: {solution.total_duration_minutes} minutes")
    print("-" * 80)

    all_slots = sorted(solution.schedule.keys())
    for slot in all_slots:
        events_in_slot = solution.schedule[slot]
        start_time_minutes = 9 * 60 + slot * solution.slot_duration_minutes
        start_time = f"{start_time_minutes // 60}:{(start_time_minutes % 60):02d}"

        event_descriptions: list[str] = []
        for e in events_in_slot:
            event_group = e["event"]
            # Format event name for EventGroup
            if len(event_group.events) == 1:
                # Single event in group - show specific category
                single_event = event_group.events[0]
                event_name = (
                    f"{event_group.event_type.value} {single_event.age_category.value}"
                )
            else:
                # Multiple events in group - show all categories
                categories = [e.age_category.value for e in event_group.events]
                # Sort categories for consistent display
                categories.sort()
                categories_str = "/".join(categories)
                event_name = f"{event_group.event_type.value} {categories_str}"

            if e.get("is_start", True):
                event_descriptions.append(f"🟢 {event_name} (START)")
            else:
                offset = e.get("slot_offset", 0)
                event_descriptions.append(f"🔵 {event_name} (slot {offset + 1})")

        print(f"Slot {slot:2d} ({start_time}): {', '.join(event_descriptions)}")


def group_events_by_type(events: list[Event], athletes: list[Athlete], *, mix_genders_track: bool = False) -> list[EventGroup]:
    """Group individual events by type into EventGroups for scheduling with smart merging."""

    # Count actual athletes per event
    athlete_counts = _count_athletes_per_event_real(events, athletes)

    # Organize events by type
    events_by_type: dict[EventType, list[Event]] = {}
    for event in events:
        if event.event_type not in events_by_type:
            events_by_type[event.event_type] = []
        events_by_type[event.event_type].append(event)

    # Build field groups with default (wide) tiers
    field_tiers = _FIELD_TIERS_DEFAULT
    field_groups = _build_field_groups(events_by_type, athlete_counts, field_tiers)

    # Check cross-venue conflict density; split tiers if needed
    if _has_excessive_cross_venue_conflicts(field_groups, athletes):
        field_tiers = _FIELD_TIERS_SPLIT
        field_groups = _build_field_groups(events_by_type, athlete_counts, field_tiers)

    # Check gender-asymmetric blocking; gender-split affected tiers if needed
    gender_split_tiers = _check_gender_split_needed(field_groups, athletes, field_tiers)
    if gender_split_tiers:
        field_groups = _build_field_groups(
            events_by_type, athlete_counts, field_tiers, gender_split_tiers
        )

    # Build track groups (unaffected by field tier choice)
    event_groups: list[EventGroup] = []
    for event_type, events_of_type in events_by_type.items():
        if EventVenueMapping.get(event_type) == Venue.TRACK:
            event_groups.extend(
                _create_track_groups(event_type, events_of_type, athlete_counts, mix_genders=mix_genders_track)
            )
    event_groups.extend(field_groups)

    # Sanity check: every input event must appear in exactly one group
    grouped_event_ids: set[str] = set()
    for g in event_groups:
        for e in g.events:
            if e.id in grouped_event_ids:
                raise ValueError(f"Event {e.id} appears in multiple groups")
            grouped_event_ids.add(e.id)
    input_event_ids = {e.id for e in events}
    missing = input_event_ids - grouped_event_ids
    if missing:
        raise ValueError(f"Events not assigned to any group: {', '.join(sorted(missing))}")

    return event_groups


def _build_field_groups(
    events_by_type: dict[EventType, list[Event]],
    athlete_counts: dict[str, int],
    tiers: list[tuple[list[str], str]],
    gender_split_tiers: set[str] | None = None,
) -> list[EventGroup]:
    """Build all field event groups using the given tier configuration."""
    groups: list[EventGroup] = []
    for event_type, events_of_type in events_by_type.items():
        if EventVenueMapping.get(event_type) != Venue.TRACK:
            groups.extend(
                _create_field_groups(
                    event_type, events_of_type, athlete_counts, tiers,
                    gender_split_tiers=gender_split_tiers,
                )
            )
    return groups


def _has_excessive_cross_venue_conflicts(
    field_groups: list[EventGroup], athletes: list[Athlete],
) -> bool:
    """Check if any two field groups at different venues share too many athletes.

    When this happens, the groups can't run in parallel, destroying packability.
    Returns True if the 11-14 tier should be split.

    Only considers groups that contain 11-14 categories (the splittable tier).
    Rekrutt and 15+ groups are unsplittable by design.
    """
    from .models import get_venue_for_event

    # Categories in the 11-14 tier (the only one we can split)
    splittable_categories = {
        cat for cats, _ in _FIELD_TIERS_DEFAULT for cat in cats
        if cat not in ["J-Rekrutt", "G-Rekrutt"]  # exclude Rekrutt
    } - {
        cat for cats, name in _FIELD_TIERS_DEFAULT if name == "15+"
        for cat in cats
    }

    def _has_splittable_category(group: EventGroup) -> bool:
        return any(e.age_category.value in splittable_categories for e in group.events)

    # Only check groups containing 11-14 categories
    candidates = [g for g in field_groups if _has_splittable_category(g)]
    if not candidates:
        return False

    # Map individual event ID -> group ID
    event_to_group: dict[str, str] = {}
    for g in field_groups:
        for e in g.events:
            event_to_group[e.id] = g.id

    # Map group ID -> set of athlete names
    group_athletes: dict[str, set[str]] = {g.id: set() for g in field_groups}
    for a in athletes:
        for e in a.events:
            gid = event_to_group.get(e.id)
            if gid is not None:
                group_athletes[gid].add(a.name)

    # Map group ID -> venue
    group_venue: dict[str, Venue | None] = {}
    for g in field_groups:
        first = g.events[0]
        group_venue[g.id] = get_venue_for_event(g.event_type, first.age_category)

    # Check pairs where at least one group is a splittable candidate
    for g1 in candidates:
        # Check against ALL field groups (not just candidates)
        for g2 in field_groups:
            if g2.id <= g1.id:
                continue  # avoid duplicates
            if group_venue[g1.id] == group_venue[g2.id]:
                continue  # same venue — already sequential
            shared = len(group_athletes[g1.id] & group_athletes[g2.id])
            if shared > _MAX_CROSS_VENUE_SHARED_ATHLETES:
                print(
                    f"  ⚠️  Cross-venue conflict: {g1.id} & {g2.id} "
                    f"share {shared} athletes — splitting 11-14 tier"
                )
                return True

    return False


def _check_gender_split_needed(
    field_groups: list[EventGroup],
    athletes: list[Athlete],
    tiers: list[tuple[list[str], str]],
) -> set[str]:
    """Check if any mixed-gender field groups would benefit from gender splitting.

    Returns tier names that should be gender-split.

    A tier needs gender splitting when a mixed-gender group shares athletes of
    only one gender with a long-duration cross-venue group — the other gender
    is being held back unnecessarily.
    """
    from .models import get_venue_for_event

    # Category -> tier name
    tier_lookup: dict[str, str] = {}
    for categories, tier_name in tiers:
        for cat in categories:
            tier_lookup[cat] = tier_name

    # Event -> group, group lookup
    event_to_group: dict[str, str] = {}
    group_by_id: dict[str, EventGroup] = {}
    for g in field_groups:
        group_by_id[g.id] = g
        for e in g.events:
            event_to_group[e.id] = g.id

    # Athlete -> is_boy (determined from their event categories)
    athlete_is_boy: dict[str, bool] = {}
    for a in athletes:
        for e in a.events:
            if _is_boys_category(e.age_category.value):
                athlete_is_boy[a.name] = True
                break
        athlete_is_boy.setdefault(a.name, False)

    # Group -> set of athlete names
    group_athletes: dict[str, set[str]] = {g.id: set() for g in field_groups}
    for a in athletes:
        for e in a.events:
            gid = event_to_group.get(e.id)
            if gid is not None:
                group_athletes[gid].add(a.name)

    # Group -> venue
    group_venue: dict[str, Venue | None] = {}
    for g in field_groups:
        group_venue[g.id] = get_venue_for_event(g.event_type, g.events[0].age_category)

    tiers_to_split: set[str] = set()

    for g in field_groups:
        # Only consider mixed-gender groups
        has_boys = any(_is_boys_category(e.age_category.value) for e in g.events)
        has_girls = any(not _is_boys_category(e.age_category.value) for e in g.events)
        if not (has_boys and has_girls):
            continue

        group_tier = tier_lookup.get(g.events[0].age_category.value)
        if group_tier is None or group_tier in tiers_to_split:
            continue

        # Skip small groups — splitting them just creates more groups without saving time
        group_athlete_count = len(group_athletes[g.id])
        if group_athlete_count < _MIN_GROUP_SIZE_FOR_GENDER_SPLIT:
            continue

        # Check each cross-venue group for single-gender blocking
        for other in field_groups:
            if other.id == g.id:
                continue
            if group_venue[other.id] == group_venue[g.id]:
                continue  # same venue — already sequential
            if other.duration_minutes < _MIN_BLOCKING_DURATION_FOR_GENDER_SPLIT:
                continue

            shared = group_athletes[g.id] & group_athletes[other.id]
            if not shared:
                continue

            shared_boys = {a for a in shared if athlete_is_boy.get(a, False)}
            shared_girls = shared - shared_boys

            # Long groups are worth splitting even with 1 shared athlete
            min_shared = 1 if g.duration_minutes > _MAX_UNSPLIT_FIELD_DURATION else _MIN_SHARED_FOR_GENDER_SPLIT

            if shared_boys and not shared_girls and len(shared_boys) >= min_shared:
                print(
                    f"  ⚠️  Gender-asymmetric blocking: {g.id} & {other.id} "
                    f"share {len(shared_boys)} boys — splitting tier '{group_tier}' by gender"
                )
                tiers_to_split.add(group_tier)
            elif shared_girls and not shared_boys and len(shared_girls) >= min_shared:
                print(
                    f"  ⚠️  Gender-asymmetric blocking: {g.id} & {other.id} "
                    f"share {len(shared_girls)} girls — splitting tier '{group_tier}' by gender"
                )
                tiers_to_split.add(group_tier)

    return tiers_to_split


def _count_athletes_per_event_real(events: list[Event], athletes: list[Athlete]) -> dict[str, int]:
    """Count how many athletes are registered for each individual event based on actual registration data."""
    athlete_counts = {}
    
    # Initialize all events with 0 count
    for event in events:
        athlete_counts[event.id] = 0
    
    # Count athletes registered for each event
    for athlete in athletes:
        for event in athlete.events:
            if event.id in athlete_counts:
                athlete_counts[event.id] += 1
    
    return athlete_counts


def _is_boys_category(category: str) -> bool:
    """Check if a category is for boys/men."""
    return category.startswith("G") or category == "Menn Senior"


def _create_track_groups_for_gender(
    event_type: EventType,
    events: list[Event],
    athlete_counts: dict[str, int],
    age_ranges: list[tuple[list[str], str]],
) -> list[EventGroup]:
    """Create track event groups for a single gender with age-based merging."""
    groups: list[EventGroup] = []
    remaining_events = events.copy()

    for age_categories, range_name in age_ranges:
        range_events = [e for e in remaining_events if e.age_category.value in age_categories]
        if not range_events:
            continue

        total_athletes = sum(athlete_counts.get(e.id, 0) for e in range_events)

        if len(range_events) == 1:
            event = range_events[0]
            group_id = f"{event_type.value}_{event.age_category.value}_group"
            groups.append(EventGroup(id=group_id, event_type=event_type, events=[event]))
            remaining_events.remove(event)
        elif total_athletes <= 8:
            group_id = f"{event_type.value}_{range_name}_group"
            groups.append(EventGroup(id=group_id, event_type=event_type, events=range_events))
            for event in range_events:
                remaining_events.remove(event)
        else:
            range_events.sort(key=lambda e: athlete_counts.get(e.id, 0))
            current_group: list[Event] = []
            current_count = 0

            for event in range_events:
                event_count = athlete_counts.get(event.id, 0)
                if current_count + event_count <= 8 and current_group:
                    current_group.append(event)
                    current_count += event_count
                else:
                    if current_group:
                        if len(current_group) == 1:
                            group_id = f"{event_type.value}_{current_group[0].age_category.value}_group"
                        else:
                            categories = [e.age_category.value for e in current_group]
                            group_id = f"{event_type.value}_{'_'.join(categories)}_group"
                        groups.append(EventGroup(id=group_id, event_type=event_type, events=current_group))
                        for e in current_group:
                            remaining_events.remove(e)
                    current_group = [event]
                    current_count = event_count

            if current_group:
                if len(current_group) == 1:
                    group_id = f"{event_type.value}_{current_group[0].age_category.value}_group"
                else:
                    categories = [e.age_category.value for e in current_group]
                    group_id = f"{event_type.value}_{'_'.join(categories)}_group"
                groups.append(EventGroup(id=group_id, event_type=event_type, events=current_group))
                for e in current_group:
                    remaining_events.remove(e)

    for event in remaining_events:
        group_id = f"{event_type.value}_{event.age_category.value}_group"
        groups.append(EventGroup(id=group_id, event_type=event_type, events=[event]))

    return groups


def _create_hurdle_groups_for_gender(
    event_type: EventType,
    events: list[Event],
    athlete_counts: dict[str, int],
) -> list[EventGroup]:
    """Create hurdle event groups respecting distance and height constraints.

    Events with different distance_between_m cannot share a heat (hurdle positions differ).
    Events with different height_cm can share a heat but need a gutter lane between
    height zones, reducing capacity from 8 to 8-(num_heights-1).
    """
    if not events:
        return []

    # Sub-group by distance_between_m
    by_distance: dict[float, list[Event]] = {}
    no_spec: list[Event] = []
    for e in events:
        spec = get_hurdle_spec(event_type, e.age_category)
        if spec is None:
            no_spec.append(e)
        else:
            by_distance.setdefault(spec.distance_between_m, []).append(e)

    groups: list[EventGroup] = []

    for _distance, dist_events in sorted(by_distance.items()):
        # Sort by height so same-height events are adjacent (minimizes gutters when splitting)
        dist_events.sort(key=lambda e: (
            get_hurdle_spec(event_type, e.age_category).height_cm,  # type: ignore[union-attr]
            e.age_category.value,
        ))

        capacity = hurdle_lane_capacity(event_type, [e.age_category for e in dist_events])
        total_athletes = sum(athlete_counts.get(e.id, 0) for e in dist_events)

        if total_athletes <= capacity:
            # Fits in one heat
            groups.append(_make_track_group(event_type, dist_events))
        else:
            # Greedy-pack events, sorted by height to keep same heights together
            current: list[Event] = []
            current_count = 0
            for e in dist_events:
                ec = athlete_counts.get(e.id, 0)
                cap = hurdle_lane_capacity(event_type, [x.age_category for x in current + [e]])
                if current and current_count + ec > cap:
                    groups.append(_make_track_group(event_type, current))
                    current = []
                    current_count = 0
                current.append(e)
                current_count += ec
            if current:
                groups.append(_make_track_group(event_type, current))

    # Events without specs get their own group
    for e in no_spec:
        group_id = f"{event_type.value}_{e.age_category.value}_group"
        groups.append(EventGroup(id=group_id, event_type=event_type, events=[e]))

    return groups


def _make_track_group(event_type: EventType, events: list[Event]) -> EventGroup:
    """Build an EventGroup for track events with a descriptive ID."""
    if len(events) == 1:
        gid = f"{event_type.value}_{events[0].age_category.value}_group"
    else:
        cats = "+".join(e.age_category.value for e in events)
        gid = f"{event_type.value}_{cats}_group"
    return EventGroup(id=gid, event_type=event_type, events=events)


def _create_track_groups(event_type: EventType, events: list[Event], athlete_counts: dict[str, int], *, mix_genders: bool = False) -> list[EventGroup]:
    """Create track event groups with smart age-based merging.

    When mix_genders is False (default), genders are kept separate.
    When True, genders are mixed — useful for youth events where boys and girls
    can share heats (especially hurdles with identical setups).
    """
    if mix_genders:
        # Hurdle events: group all genders together by distance/height
        if is_hurdles_event(event_type):
            return _create_hurdle_groups_for_gender(event_type, events, athlete_counts)

        # Regular track: combined age ranges across genders
        mixed_age_ranges = [
            (["G-Rekrutt", "J-Rekrutt"], "Rekrutt"),
            (["G11", "J11", "G12", "J12", "G13", "J13", "G14", "J14"], "11-14"),
            (["G15", "J15", "G16", "J16", "G17", "J17", "G18-19", "J18-19",
              "Menn Senior", "Kvinner Senior"], "15+"),
        ]
        return _create_track_groups_for_gender(event_type, events, athlete_counts, mixed_age_ranges)

    # Default: split by gender
    boys_events = [e for e in events if _is_boys_category(e.age_category.value)]
    girls_events = [e for e in events if not _is_boys_category(e.age_category.value)]

    # Hurdle events need special grouping by distance/height
    if is_hurdles_event(event_type):
        groups: list[EventGroup] = []
        groups.extend(_create_hurdle_groups_for_gender(event_type, boys_events, athlete_counts))
        groups.extend(_create_hurdle_groups_for_gender(event_type, girls_events, athlete_counts))
        return groups

    # Age ranges for boys: 3 tiers (Rekrutt | 11-14 | 15+)
    boys_age_ranges = [
        (["G-Rekrutt"], "G-Rekrutt"),
        (["G11", "G12", "G13", "G14"], "G11-14"),
        (["G15", "G16", "G17", "G18-19", "Menn Senior"], "G15+"),
    ]

    # Age ranges for girls: 3 tiers (Rekrutt | 11-14 | 15+)
    girls_age_ranges = [
        (["J-Rekrutt"], "J-Rekrutt"),
        (["J11", "J12", "J13", "J14"], "J11-14"),
        (["J15", "J16", "J17", "J18-19", "Kvinner Senior"], "J15+"),
    ]

    groups = []
    groups.extend(_create_track_groups_for_gender(event_type, boys_events, athlete_counts, boys_age_ranges))
    groups.extend(_create_track_groups_for_gender(event_type, girls_events, athlete_counts, girls_age_ranges))

    return groups


_FIELD_TIERS_DEFAULT: list[tuple[list[str], str]] = [
    (["J-Rekrutt", "G-Rekrutt"], "Rekrutt"),
    (["J11", "J12", "J13", "J14", "G11", "G12", "G13", "G14"], "11-14"),
    (["J15", "J16", "J17", "J18-19", "Kvinner Senior",
      "G15", "G16", "G17", "G18-19", "Menn Senior"], "15+"),
]

_FIELD_TIERS_SPLIT: list[tuple[list[str], str]] = [
    (["J-Rekrutt", "G-Rekrutt"], "Rekrutt"),
    (["J11", "J12", "G11", "G12"], "11-12"),
    (["J13", "J14", "G13", "G14"], "13-14"),
    (["J15", "J16", "J17", "J18-19", "Kvinner Senior",
      "G15", "G16", "G17", "G18-19", "Menn Senior"], "15+"),
]

# Maximum athletes per field event group before splitting
_MAX_FIELD_GROUP_ATHLETES = 15

# If two field groups at different venues share more than this many athletes,
# the 11-14 tier is too wide and should be split into 11-12 / 13-14.
_MAX_CROSS_VENUE_SHARED_ATHLETES = 5

# If a mixed-gender group shares athletes of only one gender with a cross-venue
# group longer than this, the tier should be gender-split.
_MIN_BLOCKING_DURATION_FOR_GENDER_SPLIT = 25  # minutes

# Only consider gender splitting for groups with at least this many athletes.
# Splitting tiny groups just creates more scheduling units without saving time.
_MIN_GROUP_SIZE_FOR_GENDER_SPLIT = 4

# Only split by gender if at least this many athletes of one gender are shared
# with the blocking group. A single shared athlete isn't worth splitting the tier
# unless the group is very long (> _MAX_UNSPLIT_FIELD_DURATION minutes).
_MIN_SHARED_FOR_GENDER_SPLIT = 2

# Groups longer than this are split even with a single shared athlete,
# because the long contiguous block makes scheduling infeasible.
_MAX_UNSPLIT_FIELD_DURATION = 50


def _create_field_groups(
    event_type: EventType,
    events: list[Event],
    athlete_counts: dict[str, int],
    tiers: list[tuple[list[str], str]] = _FIELD_TIERS_DEFAULT,
    gender_split_tiers: set[str] | None = None,
) -> list[EventGroup]:
    """Create field EventGroups by merging categories within age tiers.

    Groups events into age tiers at the same venue, mixing genders.
    Tiers in gender_split_tiers are further sub-split by gender.
    Splits groups that exceed the athlete threshold.
    """
    from .models import get_venue_for_event

    if gender_split_tiers is None:
        gender_split_tiers = set()

    # Group events by (venue, age_tier)
    tier_lookup: dict[str, str] = {}
    for categories, tier_name in tiers:
        for cat in categories:
            tier_lookup[cat] = tier_name

    buckets: dict[tuple[Venue | None, str], list[Event]] = {}
    for e in events:
        venue = get_venue_for_event(event_type, e.age_category)
        tier = tier_lookup.get(e.age_category.value, "other")
        if tier in gender_split_tiers:
            # Sub-split by gender
            gender = "B" if _is_boys_category(e.age_category.value) else "G"
            buckets.setdefault((venue, f"{tier}_{gender}"), []).append(e)
        else:
            buckets.setdefault((venue, tier), []).append(e)

    groups: list[EventGroup] = []
    for (venue, tier), tier_events in buckets.items():
        total_athletes = sum(athlete_counts.get(e.id, 0) for e in tier_events)

        if total_athletes <= _MAX_FIELD_GROUP_ATHLETES:
            # Whole tier fits in one group
            groups.append(_make_field_group(event_type, tier_events))
        else:
            # Split: greedily pack events sorted by athlete count
            tier_events.sort(key=lambda e: athlete_counts.get(e.id, 0))
            current: list[Event] = []
            current_count = 0
            for e in tier_events:
                ec = athlete_counts.get(e.id, 0)
                if current and current_count + ec > _MAX_FIELD_GROUP_ATHLETES:
                    groups.append(_make_field_group(event_type, current))
                    current = []
                    current_count = 0
                current.append(e)
                current_count += ec
            if current:
                groups.append(_make_field_group(event_type, current))

    return groups


def _make_field_group(
    event_type: EventType, events: list[Event],
) -> EventGroup:
    """Build an EventGroup with a descriptive ID."""
    if len(events) == 1:
        gid = f"{event_type.value}_{events[0].age_category.value}_group"
    else:
        cats = "+".join(e.age_category.value for e in events)
        gid = f"{event_type.value}_{cats}_group"
    return EventGroup(id=gid, event_type=event_type, events=events)


def test_isonen_parser() -> tuple[list[EventGroup], list[Athlete]]:
    """Test the Isonen CSV parser with the example file."""
    print("Testing Isonen CSV parser...")

    try:
        events, athletes = parse_isonen_csv("/Users/asgramme/Downloads/Deltakerliste - Seriestevne 1.csv")

        print(f"\n📊 Parsed Results:")
        print(f"Events: {len(events)}")
        print(f"Athletes: {len(athletes)}")

        print(f"\n📅 Events by type:")
        event_types: dict[str, list[Event]] = {}
        for event in events:
            event_type = event.event_type.value
            if event_type not in event_types:
                event_types[event_type] = []
            event_types[event_type].append(event)

        for event_type, events_of_type in event_types.items():
            print(f"  {event_type}: {len(events_of_type)} categories")
            for event in events_of_type:
                print(
                    f"    - {event.age_category.value} ({event.duration_minutes}min, {event.personnel_required} personnel)"
                )

        print(f"\n👥 Sample athletes:")
        for athlete in athletes[:5]:  # Show first 5 athletes
            event_names = [
                f"{e.event_type.value} {e.age_category.value}" for e in athlete.events
            ]
            print(f"  {athlete.name}: {', '.join(event_names)}")

        if len(athletes) > 5:
            print(f"  ... and {len(athletes) - 5} more athletes")

        # Group events by type for scheduling
        event_groups = group_events_by_type(events, athletes)
        print(f"\n📋 Created {len(event_groups)} event groups")
        for group in event_groups:
            print(
                f"  {group.id}: {len(group.events)} events ({group.duration_minutes} min total)"
            )

        return event_groups, athletes

    except Exception as e:
        print(f"❌ Error parsing CSV: {e}")
        raise


def solve_isonen_test() -> SchedulingResult:
    """Test with data from Isonen CSV"""
    print("\nTesting with Isonen CSV data...")
    events, athletes = test_isonen_parser()

    # Use functional scheduler
    solution = schedule_track_meet(
        events=events,
        athletes=athletes,
        total_personnel=30,  # Increased for larger event set
        max_time_slots=24,  # 2 hours - spread events to use available time
        timeout_ms=10000,
        optimization_timeout_ms=10000,
    )

    if solution.status == "solved":
        print(f"\n✅ Solution found for Isonen data!")
        print(f"Total time slots: {solution.total_slots}")
        print(f"Total duration: {solution.total_duration_minutes} minutes")

        # Print optimization stats if available
        if solution.optimization_stats:
            stats = solution.optimization_stats
            improvement = stats['initial_slots'] - stats['final_slots']
            print(
                f"Optimization: {stats['initial_slots']} → {stats['final_slots']} slots (improved by {improvement})"
            )
            if 'young_finish_slot' in stats:
                print(f"Young athletes finish by slot {stats['young_finish_slot']}")
            if 'older_min_gap_slots' in stats:
                print(f"Older athlete min gap: {stats['older_min_gap_slots']} slots")

        # Generate HTML report automatically
        generate_html_report(
            solution_dict=solution,
            title="Track Meet Schedule - Isonen Data",
            filename="isonen_schedule.html",
        )

        # Generate updated CSV with computed start times
        from .csv_exporter import export_schedule_csv

        export_schedule_csv(
            result=solution,
            original_csv_path="/Users/asgramme/Downloads/Deltakerliste - Seriestevne 1.csv",
            output_path="isonen_schedule.csv",
            start_hour=9,
            start_minute=0,
        )

        # Full schedule will be printed in main
    else:
        print(f"❌ Status: {solution.status}")

    return solution


def generate_html_report(
    solution_dict: SchedulingResult,
    title: str,
    filename: str,
) -> None:
    """Generate an HTML report from a scheduling solution."""
    if solution_dict.status != "solved":
        print(f"❌ Cannot generate HTML report: {solution_dict.status}")
        return

    # Generate and save HTML report
    print(f"\n📊 Generating HTML report: {filename}")
    save_html_schedule(
        result=solution_dict,
        file_path=filename,
        title=title,
        start_hour=9,
        start_minute=0,
    )

    import os

    print(f"✅ HTML report saved: {os.path.abspath(filename)}")
    print(f"🌐 Open the file in your browser to view the schedule visualization")


if __name__ == "__main__":
    # Test with real data from CSV (may be more complex)
    print("=== Testing Z3 Solver (Isonen Data) ===")
    start_time = time.time()
    isonen_solution = solve_isonen_test()
    isonen_time = time.time() - start_time

    print(f"Z3 solver with Isonen data: {isonen_time:.3f} seconds")
    if isonen_solution.status == "solved":
        print(
            f"Result: {isonen_solution.total_slots} slots, {isonen_solution.total_duration_minutes} minutes"
        )
        print_full_schedule(isonen_solution, "Isonen Data Schedule")

    print("\n" + "=" * 50)
    print("Testing complete!")
    if isonen_solution.status == "solved":
        print("HTML report generated: isonen_schedule.html")
    print("Open the HTML files in your browser to view the schedule visualizations!")
