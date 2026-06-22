import time

from .functional_scheduler import SchedulingResult, schedule_track_meet
from .html_schedule_generator import save_html_schedule
from .isonen_parser import parse_isonen_xlsx
from .models import (
    Athlete, Event, EventGroup, EventType, EventVenueMapping,
    MASTERS_MEN, MASTERS_WOMEN, Venue,
    get_category_age_order, get_hurdle_spec, hurdle_lane_capacity,
    is_hurdles_event, mixed_hurdle_lane_capacity,
)


# Category-string lists for tier configuration, derived once from the
# centralized masters sets in models.py.
_MASTERS_MEN_VALUES: list[str] = sorted(c.value for c in MASTERS_MEN)
_MASTERS_WOMEN_VALUES: list[str] = sorted(c.value for c in MASTERS_WOMEN)
_MASTERS_ALL_VALUES: list[str] = _MASTERS_MEN_VALUES + _MASTERS_WOMEN_VALUES


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


def group_events_by_type(events: list[Event], athletes: list[Athlete], *, mix_genders_track: bool = False, mix_hurdle_distances: bool = False) -> list[EventGroup]:
    """Group individual events by type into EventGroups for scheduling with smart merging."""

    # Count actual athletes per event
    athlete_counts = _count_athletes_per_event_real(events, athletes)

    # Organize events by type
    events_by_type: dict[EventType, list[Event]] = {}
    for event in events:
        if event.event_type not in events_by_type:
            events_by_type[event.event_type] = []
        events_by_type[event.event_type].append(event)

    # Build field groups. Youth is split into 11-12 / 13-14 tiers.
    field_tiers = _FIELD_TIERS_DEFAULT
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
                _create_track_groups(event_type, events_of_type, athlete_counts, mix_genders=mix_genders_track, mix_hurdle_distances=mix_hurdle_distances)
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

    # Validate no forbidden cross-tier combinations
    _validate_no_forbidden_combinations(event_groups, athlete_counts)

    return event_groups


def _validate_no_forbidden_combinations(
    groups: list[EventGroup], athlete_counts: dict[str, int],
) -> None:
    """Assert that no group contains a forbidden combination.

    Applies to both track and field groups:
      - Rekrutt mixed with any non-Rekrutt → forbidden (Rekrutt is isolated)

    Track-only rules:
      - 11-14 (G11..G14, J11..J14) with 18-19, Senior, or Masters → forbidden
      - Track heat exceeding 8 athletes → forbidden (hard lane cap)

    Field group oversize is permitted (soft cap with warning emitted at split
    time). Field cross-tier combinations other than Rekrutt mixing are permitted.
    """
    for g in groups:
        cats = {e.age_category.value for e in g.events}
        has_rekrutt = bool(cats & _CATEGORIES_REKRUTT)
        has_non_rekrutt = bool(cats - _CATEGORIES_REKRUTT)
        if has_rekrutt and has_non_rekrutt:
            raise ValueError(
                f"Forbidden combination in group {g.id}: Rekrutt mixed "
                f"with non-Rekrutt (categories: {sorted(cats)})"
            )

        if EventVenueMapping.get(g.event_type) != Venue.TRACK:
            continue  # remaining checks are track-only

        has_11_14 = bool(cats & _CATEGORIES_11_14)
        has_18_plus = bool(cats & _CATEGORIES_18_PLUS_NONMASTERS)
        has_masters = bool(cats & _CATEGORIES_MASTERS)
        if has_11_14 and (has_18_plus or has_masters):
            raise ValueError(
                f"Forbidden combination in track group {g.id}: 11-14 with "
                f"18+/Sr/Masters (categories: {sorted(cats)})"
            )
        count = _bucket_athlete_count(g.events, athlete_counts)
        if count > _MAX_FIELD_GROUP_ATHLETES and len(g.events) > 1:
            raise ValueError(
                f"Track group {g.id} exceeds lane cap of "
                f"{_MAX_FIELD_GROUP_ATHLETES}: {count} athletes "
                f"across {len(g.events)} categories"
            )


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
    """Check if a category is for boys/men (incl. MV* masters)."""
    return category.startswith("G") or category.startswith("MV") or category == "Menn Senior"


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


def _create_mixed_hurdle_groups_for_gender(
    event_type: EventType,
    events: list[Event],
    athlete_counts: dict[str, int],
) -> list[EventGroup]:
    """Create hurdle groups allowing different distance_between_m in one heat.

    Instead of hard-splitting by distance first, pools events within each age
    tier, sorts by (distance, height, category), and packs using
    mixed_hurdle_lane_capacity.  2 gutter lanes are reserved per distance
    boundary, 1 per height boundary within a distance zone.

    Events are never mixed across the <15 / 15+ age boundary (hard limit).
    """
    if not events:
        return []

    # Separate events with/without specs
    with_spec: list[Event] = []
    no_spec: list[Event] = []
    for e in events:
        spec = get_hurdle_spec(event_type, e.age_category)
        if spec is None:
            no_spec.append(e)
        else:
            with_spec.append(e)

    # Split into age tiers: <15 and 15+
    under15: list[Event] = []
    over15: list[Event] = []
    for e in with_spec:
        if get_category_age_order(e.age_category) < 15:
            under15.append(e)
        else:
            over15.append(e)

    groups: list[EventGroup] = []
    for pool in (under15, over15):
        groups.extend(_pack_mixed_hurdles(event_type, pool, athlete_counts))

    for e in no_spec:
        group_id = f"{event_type.value}_{e.age_category.value}_group"
        groups.append(EventGroup(id=group_id, event_type=event_type, events=[e]))

    return groups


def _pack_mixed_hurdles(
    event_type: EventType,
    events: list[Event],
    athlete_counts: dict[str, int],
) -> list[EventGroup]:
    """Pack a pool of hurdle events (mixed distances allowed) into heats.

    Events are sorted by (distance, height, category) so similar setups sit next
    to each other, then partitioned into contiguous heats each within
    mixed_hurdle_lane_capacity. The partition uses the fewest heats and, among
    those, the largest minimum heat size — so a lone athlete is not stranded in
    a heat when a more even split fits (e.g. [3,2] is chosen over [4,1]).
    """
    if not events:
        return []

    # Sort by (distance, height, category) so same-distance/height events are adjacent
    def _sort_key(e: Event) -> tuple[float, float, str]:
        spec = get_hurdle_spec(event_type, e.age_category)
        assert spec is not None
        return (spec.distance_between_m, spec.height_cm, e.age_category.value)

    events.sort(key=_sort_key)
    n = len(events)
    counts = [athlete_counts.get(e.id, 0) for e in events]
    cats = [e.age_category for e in events]

    # dp[i] = (heats, min_heat_size) for the best packing of events[i:].
    # Fewer heats wins; ties broken by a larger minimum heat size.
    dp: list[tuple[int, int]] = [(0, 10 ** 9)] * (n + 1)
    nxt: list[int] = [n] * (n + 1)
    for i in range(n - 1, -1, -1):
        best: tuple[int, int] | None = None
        seg_count = 0
        for j in range(i + 1, n + 1):
            seg_count += counts[j - 1]
            # A single event always forms a heat, even if its own count exceeds
            # the lane cap (a lone oversized category cannot be split here).
            if j > i + 1 and seg_count > mixed_hurdle_lane_capacity(event_type, cats[i:j]):
                break
            sub_heats, sub_min = dp[j]
            cand = (sub_heats + 1, min(seg_count, sub_min))
            if (
                best is None
                or cand[0] < best[0]
                or (cand[0] == best[0] and cand[1] > best[1])
            ):
                best = cand
                nxt[i] = j
        assert best is not None
        dp[i] = best

    groups: list[EventGroup] = []
    i = 0
    while i < n:
        j = nxt[i]
        groups.append(_make_track_group(event_type, events[i:j]))
        i = j

    return groups


def _make_track_group(event_type: EventType, events: list[Event]) -> EventGroup:
    """Build an EventGroup for track events with a descriptive ID."""
    if len(events) == 1:
        gid = f"{event_type.value}_{events[0].age_category.value}_group"
    else:
        cats = "+".join(e.age_category.value for e in events)
        gid = f"{event_type.value}_{cats}_group"
    return EventGroup(id=gid, event_type=event_type, events=events)


def _create_track_groups(event_type: EventType, events: list[Event], athlete_counts: dict[str, int], *, mix_genders: bool = False, mix_hurdle_distances: bool = False) -> list[EventGroup]:
    """Create track event groups with smart age-based merging.

    When mix_genders is False (default), genders are kept separate.
    When True, genders are mixed — useful for youth events where boys and girls
    can share heats (especially hurdles with identical setups).

    When mix_hurdle_distances is True, hurdle events with different distance_between_m
    can share a heat (at the cost of 2 gutter lanes per distance boundary).

    For non-hurdle track events, after per-tier groups are built, a min-size
    rescue pass attempts allowed cross-tier merges (Rules A and B) to lift
    tiny heats (<4 athletes) to >=4 — provided the merged size stays <=8 (the
    hard lane cap).
    """
    hurdle_fn = _create_mixed_hurdle_groups_for_gender if mix_hurdle_distances else _create_hurdle_groups_for_gender

    if mix_genders:
        # Hurdle events: group all genders together by distance/height
        if is_hurdles_event(event_type):
            return hurdle_fn(event_type, events, athlete_counts)

        # Regular track: combined age ranges across genders
        mixed_age_ranges = [
            (["G-Rekrutt", "J-Rekrutt"], "Rekrutt"),
            (["G11", "J11", "G12", "J12", "G13", "J13", "G14", "J14"], "11-14"),
            (["G15", "J15", "G16", "J16", "G17", "J17", "G18-19", "J18-19",
              "Menn Senior", "Kvinner Senior"], "15+"),
            (_MASTERS_ALL_VALUES, "Masters"),
        ]
        groups = _create_track_groups_for_gender(event_type, events, athlete_counts, mixed_age_ranges)
        _rescue_tiny_track_groups(event_type, groups, athlete_counts)
        return groups

    # Default: split by gender
    boys_events = [e for e in events if _is_boys_category(e.age_category.value)]
    girls_events = [e for e in events if not _is_boys_category(e.age_category.value)]

    # Hurdle events need special grouping by distance/height (rescue skipped — see
    # CONSTRAINTS.md; hurdles have their own capacity rules driven by distance/height).
    if is_hurdles_event(event_type):
        groups = []
        groups.extend(hurdle_fn(event_type, boys_events, athlete_counts))
        groups.extend(hurdle_fn(event_type, girls_events, athlete_counts))
        return groups

    # Age ranges for boys: 4 tiers (Rekrutt | 11-14 | 15+ | Masters)
    boys_age_ranges = [
        (["G-Rekrutt"], "G-Rekrutt"),
        (["G11", "G12", "G13", "G14"], "G11-14"),
        (["G15", "G16", "G17", "G18-19", "Menn Senior"], "G15+"),
        (_MASTERS_MEN_VALUES, "G-Masters"),
    ]

    # Age ranges for girls: 4 tiers (Rekrutt | 11-14 | 15+ | Masters)
    girls_age_ranges = [
        (["J-Rekrutt"], "J-Rekrutt"),
        (["J11", "J12", "J13", "J14"], "J11-14"),
        (["J15", "J16", "J17", "J18-19", "Kvinner Senior"], "J15+"),
        (_MASTERS_WOMEN_VALUES, "J-Masters"),
    ]

    groups = []
    boys_groups = _create_track_groups_for_gender(event_type, boys_events, athlete_counts, boys_age_ranges)
    _rescue_tiny_track_groups(event_type, boys_groups, athlete_counts)
    groups.extend(boys_groups)
    girls_groups = _create_track_groups_for_gender(event_type, girls_events, athlete_counts, girls_age_ranges)
    _rescue_tiny_track_groups(event_type, girls_groups, athlete_counts)
    groups.extend(girls_groups)

    return groups


def _track_group_is_youth_11_14(group: EventGroup) -> bool:
    """True if the group consists entirely of 11-14 categories."""
    return all(e.age_category.value in _CATEGORIES_11_14 for e in group.events)


def _track_group_is_masters(group: EventGroup) -> bool:
    """True if the group consists entirely of Masters categories."""
    return all(e.age_category.value in _CATEGORIES_MASTERS for e in group.events)


def _track_group_is_fifteen_plus(group: EventGroup) -> bool:
    """True if the group is the 15+ tier (15-17 + 18-19 + Sr, no masters, no <15)."""
    fifteen_plus = _CATEGORIES_15_17 | _CATEGORIES_18_PLUS_NONMASTERS
    return (
        all(e.age_category.value in fifteen_plus for e in group.events)
        and any(e.age_category.value in fifteen_plus for e in group.events)
    )


def _track_group_count(group: EventGroup, athlete_counts: dict[str, int]) -> int:
    return _bucket_athlete_count(group.events, athlete_counts)


def _rescue_tiny_track_groups(
    event_type: EventType,
    groups: list[EventGroup],
    athlete_counts: dict[str, int],
) -> None:
    """Mutate `groups` in place: merge tiny (<4) heats with adjacent eligible
    tiers per Rules A and B, but only if the merged size stays <=8.

    Rules are applied in this priority order (no conflict; Masters never touches
    15-17):
      - Rule A: tiny Masters <-> 15+ (either direction)
      - Rule B: tiny 11-14 <-> 15-17 subset of 15+ (detach 15-17 from 15+)
      - Rule B reverse: tiny 15-17-only group <-> 11-14
    """
    _apply_rule_a_track(event_type, groups, athlete_counts)
    _apply_rule_b_track(event_type, groups, athlete_counts)


def _apply_rule_a_track(
    event_type: EventType,
    groups: list[EventGroup],
    athlete_counts: dict[str, int],
) -> None:
    """Merge tiny Masters group with 15+ group at same gender if combined <= 8."""
    # Find a Masters group and a 15+ group
    masters_idx = next(
        (i for i, g in enumerate(groups) if _track_group_is_masters(g)),
        None,
    )
    fifteen_idx = next(
        (i for i, g in enumerate(groups) if _track_group_is_fifteen_plus(g)),
        None,
    )
    if masters_idx is None or fifteen_idx is None:
        return
    m_count = _track_group_count(groups[masters_idx], athlete_counts)
    f_count = _track_group_count(groups[fifteen_idx], athlete_counts)
    if m_count >= _MIN_PREFERRED_GROUP_ATHLETES and f_count >= _MIN_PREFERRED_GROUP_ATHLETES:
        return
    if m_count + f_count > _MAX_FIELD_GROUP_ATHLETES:
        # Lane cap wins — small heat is better than overflow
        return
    # Merge into the 15+ group
    merged_events = groups[fifteen_idx].events + groups[masters_idx].events
    merged_group = _make_track_group(event_type, merged_events)
    # Remove the higher index first to preserve the other index
    hi, lo = sorted([masters_idx, fifteen_idx], reverse=True)
    del groups[hi]
    del groups[lo]
    groups.append(merged_group)


def _apply_rule_b_track(
    event_type: EventType,
    groups: list[EventGroup],
    athlete_counts: dict[str, int],
) -> None:
    """For tiny 11-14 groups: detach 15-17 events from same-gender 15+ group and merge in.

    Constraints:
      - Combined size must stay <=8 (hard lane cap)
      - Leaves 18-19 / Senior / Masters portion of 15+ as its own group
      - Skipped if 15+ group has no 15-17 events (only adults)
    """
    youth_idx = next(
        (i for i, g in enumerate(groups) if _track_group_is_youth_11_14(g)),
        None,
    )
    if youth_idx is None:
        return
    y_count = _track_group_count(groups[youth_idx], athlete_counts)
    if y_count >= _MIN_PREFERRED_GROUP_ATHLETES:
        return
    fifteen_idx = next(
        (i for i, g in enumerate(groups) if _track_group_is_fifteen_plus(g)),
        None,
    )
    if fifteen_idx is None:
        return
    fifteen_events = groups[fifteen_idx].events
    teens = [e for e in fifteen_events if e.age_category.value in _CATEGORIES_15_17]
    remainder = [e for e in fifteen_events if e.age_category.value not in _CATEGORIES_15_17]
    if not teens:
        return
    teens_count = sum(athlete_counts.get(e.id, 0) for e in teens)
    if y_count + teens_count > _MAX_FIELD_GROUP_ATHLETES:
        return
    youth_events = groups[youth_idx].events
    merged_youth = _make_track_group(event_type, youth_events + teens)
    # Replace the youth group; replace or remove the 15+ group
    # Remove higher index first
    hi, lo = sorted([youth_idx, fifteen_idx], reverse=True)
    if remainder:
        new_fifteen = _make_track_group(event_type, remainder)
    else:
        new_fifteen = None
    # Reconstruct without using indices after deletion
    del groups[hi]
    del groups[lo]
    groups.append(merged_youth)
    if new_fifteen is not None:
        groups.append(new_fifteen)


# Field age tiers. Youth is split into 11-12 / 13-14 so the tiny-bucket rescue
# can avoid forming an over-wide span (e.g. 11..17) when a younger group already
# stands on its own. Rekrutt (10yo) is isolated and never merges with older.
_FIELD_TIERS_DEFAULT: list[tuple[list[str], str]] = [
    (["J-Rekrutt", "G-Rekrutt"], "Rekrutt"),
    (["J11", "J12", "G11", "G12"], "11-12"),
    (["J13", "J14", "G13", "G14"], "13-14"),
    (["J15", "J16", "J17", "J18-19", "Kvinner Senior",
      "G15", "G16", "G17", "G18-19", "Menn Senior"], "15+"),
    (_MASTERS_ALL_VALUES, "Masters"),
]

# Soft split target for field event groups. Field groups may exceed this when no
# clean partition into [_MIN_PREFERRED_GROUP_ATHLETES, _MAX_FIELD_GROUP_ATHLETES]
# is possible; a warning is emitted in that case. Track heats keep 8 as a hard
# cap (lanes).
_MAX_FIELD_GROUP_ATHLETES = 8

# Strong preference: groups (both track heats and field groups) should have at
# least this many athletes. When a bucket falls below this, cross-tier merges
# per the rules in _MERGE_RULES are attempted before settling for a tiny group.
_MIN_PREFERRED_GROUP_ATHLETES = 4

# The 15-17 subset of the unified 15+ tier. When 11-14 needs to merge UP per
# Rule B, the 15-17 events are detached from a 15+ bucket and merged with the
# 11-14 bucket; the 18-19 / Senior / Masters remainder of 15+ stays separate.
_CATEGORIES_15_17: frozenset[str] = frozenset({
    "G15", "G16", "G17", "J15", "J16", "J17",
})

# 11-14 youth categories (used by Rule B). Includes both the default unified
# "11-14" tier members and the split "11-12" / "13-14" tier members.
_CATEGORIES_11_14: frozenset[str] = frozenset({
    "G11", "G12", "G13", "G14", "J11", "J12", "J13", "J14",
})

# Masters category values. Same as _MASTERS_ALL_VALUES but as a frozenset for
# O(1) membership checks during validation.
_CATEGORIES_MASTERS: frozenset[str] = frozenset(_MASTERS_ALL_VALUES)

# Adult non-masters categories that 11-14 must NEVER share a group with.
_CATEGORIES_18_PLUS_NONMASTERS: frozenset[str] = frozenset({
    "G18-19", "J18-19", "Menn Senior", "Kvinner Senior",
})

# Rekrutt category values.
_CATEGORIES_REKRUTT: frozenset[str] = frozenset({"G-Rekrutt", "J-Rekrutt"})

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

    Strongly prefers groups of >= _MIN_PREFERRED_GROUP_ATHLETES athletes, but
    keeps the merge conservative (see _rescue_tiny_field_buckets): Rekrutt is
    isolated, a group that already meets the minimum is never padded, and only
    deficient buckets are combined. Equipment sharing is venue-scoped; venue
    mapping (incl. secondary venues for Rekrutt) already enforces physical
    equipment separation.

    Field group cap (_MAX_FIELD_GROUP_ATHLETES) is a SOFT split target.
    Oversized groups are allowed with a warning when no clean partition exists.
    """
    from .models import get_venue_for_event

    if gender_split_tiers is None:
        gender_split_tiers = set()

    # Phase A: build per-(venue, tier_label) buckets
    tier_lookup: dict[str, str] = {}
    for categories, tier_name in tiers:
        for cat in categories:
            tier_lookup[cat] = tier_name

    # Bucket key: (venue, tier_label). Value: list of events.
    buckets: dict[tuple[Venue | None, str], list[Event]] = {}
    for e in events:
        venue = get_venue_for_event(event_type, e.age_category)
        tier = tier_lookup.get(e.age_category.value, "other")
        if tier in gender_split_tiers:
            gender = "B" if _is_boys_category(e.age_category.value) else "G"
            label = f"{tier}_{gender}"
        else:
            label = tier
        buckets.setdefault((venue, label), []).append(e)

    # Phase B: rescue deficient buckets (Rekrutt isolated; never pad a group
    # that already meets the minimum).
    _rescue_tiny_field_buckets(buckets, athlete_counts)

    # Phase C: split each bucket; soft-cap with warning
    groups: list[EventGroup] = []
    for (venue, tier_label), tier_events in buckets.items():
        if not tier_events:
            continue
        groups.extend(
            _split_field_bucket(event_type, tier_events, athlete_counts, tier_label, venue)
        )

    return groups


def _bucket_athlete_count(events: list[Event], athlete_counts: dict[str, int]) -> int:
    return sum(athlete_counts.get(e.id, 0) for e in events)


def _rescue_tiny_field_buckets(
    buckets: dict[tuple[Venue | None, str], list[Event]],
    athlete_counts: dict[str, int],
) -> None:
    """Conservatively merge deficient (<4) field buckets at the same venue.

    Goals (see CONSTRAINTS.md):
      - Rekrutt (10yo) is isolated: a Rekrutt bucket never merges with a
        non-Rekrutt one (and vice versa), even if that leaves it tiny.
      - Never pad a bucket that already meets the minimum. A group that can
        stand on its own (>=4) is left alone, so a younger group is not dragged
        into an over-wide age span (e.g. 11..17).
      - Phase 1: combine two deficient buckets (mutual benefit), preferring a
        combined size in [MIN, MAX].
      - Phase 2: fold a leftover solo (==1) bucket into the smallest sibling to
        avoid a one-person field event.

    Rekrutt buckets are excluded from every step. Each merge removes one bucket,
    so the loops terminate.
    """
    MIN = _MIN_PREFERRED_GROUP_ATHLETES

    def is_rekrutt(key: tuple[Venue | None, str]) -> bool:
        return key[1].startswith("Rekrutt")

    def size(key: tuple[Venue | None, str]) -> int:
        return _bucket_athlete_count(buckets[key], athlete_counts)

    def non_rekrutt_by_venue() -> dict[Venue | None, list[tuple[Venue | None, str]]]:
        by_venue: dict[Venue | None, list[tuple[Venue | None, str]]] = {}
        for key in buckets:
            if is_rekrutt(key):
                continue
            by_venue.setdefault(key[0], []).append(key)
        return by_venue

    # Phase 1: merge two deficient buckets (never pad a healthy one).
    while True:
        merged = False
        for keys_here in non_rekrutt_by_venue().values():
            deficient = sorted((k for k in keys_here if size(k) < MIN), key=size)
            if len(deficient) < 2:
                continue
            source = deficient[0]
            targets = [k for k in deficient if k != source]

            def score(k: tuple[Venue | None, str]) -> tuple[int, int]:
                combined = size(source) + size(k)
                if MIN <= combined <= _MAX_FIELD_GROUP_ATHLETES:
                    return (0, combined)  # clean fit: tightest first
                return (1, -combined)  # still tiny: largest combined first

            target = min(targets, key=score)
            buckets[target].extend(buckets[source])
            del buckets[source]
            merged = True
            break
        if not merged:
            break

    # Phase 2: fold any leftover solo bucket into the smallest sibling.
    while True:
        folded = False
        for keys_here in non_rekrutt_by_venue().values():
            if len(keys_here) < 2:
                continue
            solos = [k for k in keys_here if size(k) == 1]
            if not solos:
                continue
            source = solos[0]
            target = min((k for k in keys_here if k != source), key=size)
            buckets[target].extend(buckets[source])
            del buckets[source]
            folded = True
            break
        if not folded:
            break


def _split_field_bucket(
    event_type: EventType,
    tier_events: list[Event],
    athlete_counts: dict[str, int],
    tier_label: str,
    venue: Venue | None,
) -> list[EventGroup]:
    """Split a bucket into EventGroups.

    Algorithm:
      - If total <= _MAX_FIELD_GROUP_ATHLETES: one group.
      - Else: search for a partition where every group is in
        [_MIN_PREFERRED..._MAX_FIELD]. Pick the one with the fewest groups.
      - If no such partition exists (events too unbalanced): emit a single
        oversized group + warning. Oversize is preferred over tiny per the
        "no tiny" preference.
    """
    total = _bucket_athlete_count(tier_events, athlete_counts)
    if total <= _MAX_FIELD_GROUP_ATHLETES:
        return [_make_field_group(event_type, tier_events)]

    counts = [athlete_counts.get(e.id, 0) for e in tier_events]
    partition = _find_clean_partition(
        tier_events,
        counts,
        _MIN_PREFERRED_GROUP_ATHLETES,
        _MAX_FIELD_GROUP_ATHLETES,
    )
    if partition is not None:
        return [_make_field_group(event_type, evs) for evs in partition]

    cats = "+".join(e.age_category.value for e in tier_events)
    print(
        f"  ⚠️  Oversized field group: {event_type.value} {cats} "
        f"at {venue.value if venue else '?'} has {total} athletes "
        f"(soft cap {_MAX_FIELD_GROUP_ATHLETES}). No clean partition exists; "
        f"duration may be undercounted."
    )
    return [_make_field_group(event_type, tier_events)]


def _find_clean_partition(
    events: list[Event],
    counts: list[int],
    lo: int,
    hi: int,
) -> list[list[Event]] | None:
    """Find a partition of `events` where each subset's count-sum is in [lo, hi].

    Tries the smallest number of subsets first. Returns None if no such partition
    exists. Bounded backtracking with descending-order pruning.

    `len(events)` is typically small (≤10), so brute search is fast.
    """
    n = len(events)
    if n == 0:
        return []
    total = sum(counts)
    if total < lo:
        return None  # can't form even one group meeting min

    min_k = (total + hi - 1) // hi
    max_k = total // lo
    if min_k > max_k:
        return None

    # Sort by count descending for stronger pruning
    order = sorted(range(n), key=lambda i: -counts[i])

    for k in range(min_k, max_k + 1):
        group_indices: list[list[int]] = [[] for _ in range(k)]
        sums = [0] * k

        def backtrack(pos: int) -> bool:
            if pos == n:
                return all(lo <= s <= hi for s in sums)
            idx = order[pos]
            c = counts[idx]
            seen_empty = False
            for gi in range(k):
                if sums[gi] + c > hi:
                    continue
                # Symmetry break: only place into the first empty group
                if sums[gi] == 0:
                    if seen_empty:
                        continue
                    seen_empty = True
                group_indices[gi].append(idx)
                sums[gi] += c
                if backtrack(pos + 1):
                    return True
                group_indices[gi].pop()
                sums[gi] -= c
            return False

        if backtrack(0):
            return [[events[i] for i in g] for g in group_indices if g]
    return None


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
        events, athletes = parse_isonen_xlsx("/Users/asgramme/Downloads/Deltakerliste - Seriestevne 1.csv")

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
