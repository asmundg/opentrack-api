import time
from datetime import datetime

from .functional_scheduler import SchedulingResult, schedule_track_meet
from .html_schedule_generator import save_html_schedule
from .isonen_parser import parse_isonen_csv
from .models import Athlete, Category, Event, EventGroup, EventType, EventVenueMapping, Venue


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


def group_events_by_type(events: list[Event], athletes: list[Athlete]) -> list[EventGroup]:
    """Group individual events by type into EventGroups for scheduling with smart merging."""

    # Count actual athletes per event
    athlete_counts = _count_athletes_per_event_real(events, athletes)

    # Organize events by type
    events_by_type: dict[EventType, list[Event]] = {}
    for event in events:
        if event.event_type not in events_by_type:
            events_by_type[event.event_type] = []
        events_by_type[event.event_type].append(event)

    event_groups = []
    for event_type, events_of_type in events_by_type.items():
        venue = EventVenueMapping.get(event_type)

        if venue == Venue.TRACK:
            # Track events: smart merging by age groups
            groups = _create_track_groups(event_type, events_of_type, athlete_counts)
        else:
            # Field events: merge to get 3-8 athletes per group
            groups = _create_field_groups(event_type, events_of_type, athlete_counts)

        event_groups.extend(groups)

    return event_groups


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


def _create_track_groups(event_type: EventType, events: list[Event], athlete_counts: dict[str, int]) -> list[EventGroup]:
    """Create track event groups with smart age-based merging, keeping genders separate."""
    # Split events by gender first - boys and girls cannot be in the same track event
    boys_events = [e for e in events if _is_boys_category(e.age_category.value)]
    girls_events = [e for e in events if not _is_boys_category(e.age_category.value)]

    # Age ranges for boys
    boys_age_ranges = [
        (["G-Rekrutt"], "G-Rekrutt"),
        (["G11", "G12"], "G11/12"),
        (["G13", "G14"], "G13/14"),
        (["G15", "G16", "G17", "G18-19", "Menn Senior"], "G15+"),
    ]

    # Age ranges for girls
    girls_age_ranges = [
        (["J-Rekrutt"], "J-Rekrutt"),
        (["J11", "J12"], "J11/12"),
        (["J13", "J14"], "J13/14"),
        (["J15", "J16", "J17", "J18-19", "Kvinner Senior"], "J15+"),
    ]

    groups: list[EventGroup] = []
    groups.extend(_create_track_groups_for_gender(event_type, boys_events, athlete_counts, boys_age_ranges))
    groups.extend(_create_track_groups_for_gender(event_type, girls_events, athlete_counts, girls_age_ranges))

    return groups


def _create_field_groups(
    event_type: EventType,
    events: list[Event],
    athlete_counts: dict[str, int],
) -> list[EventGroup]:
    """Create field event groups, merging categories within age tiers.

    Goals:
    - At least MIN_TARGET (3) athletes per group for rest between attempts
    - At most MAX_TARGET (8) athletes to avoid events being too long
    - Merge within age tiers to keep similar ability levels together

    See CONSTRAINTS.md for merging rationale.
    """
    MIN_TARGET = 3  # Minimum athletes for rest between attempts
    MAX_TARGET = 8  # Maximum before event gets too long

    if not events:
        return []

    rekrutt_categories = ["G-Rekrutt", "J-Rekrutt"]
    under15_categories = ["G11", "J11", "G12", "J12", "G13", "J13", "G14", "J14"]
    over15_categories = ["G15", "J15", "G16", "J16", "G17", "J17", "G18-19", "J18-19",
                         "Menn Senior", "Kvinner Senior"]

    # Count 15+ athletes for this event type
    over15_events = [e for e in events if e.age_category.value in over15_categories]
    over15_athlete_count = sum(athlete_counts.get(e.id, 0) for e in over15_events)

    # If very few 15+ athletes, merge with 11-14 (so they don't compete alone)
    if over15_athlete_count < MIN_TARGET:
        age_tiers: list[tuple[list[str], str]] = [
            (rekrutt_categories, "Rekrutt"),
            (under15_categories + over15_categories, "11+"),
        ]
    else:
        age_tiers = [
            (rekrutt_categories, "Rekrutt"),
            (under15_categories, "11-14"),
            (over15_categories, "15+"),
        ]

    groups: list[EventGroup] = []

    for tier_categories, _ in age_tiers:
        tier_events = [e for e in events if e.age_category.value in tier_categories]
        if not tier_events:
            continue

        # Sort by category for consistent ordering within merged groups
        tier_events.sort(key=lambda e: tier_categories.index(e.age_category.value)
                         if e.age_category.value in tier_categories else 999)

        # Build groups greedily, targeting MIN_TARGET to MAX_TARGET athletes
        current_group: list[Event] = []
        current_count = 0

        for event in tier_events:
            event_count = athlete_counts.get(event.id, 0)

            # If adding this event would exceed max, finalize current group first
            if current_group and current_count + event_count > MAX_TARGET:
                groups.append(_make_field_group(event_type, current_group))
                current_group = []
                current_count = 0

            current_group.append(event)
            current_count += event_count

        # Finalize last group
        if current_group:
            # If too small, try to merge with previous group in same tier
            if current_count < MIN_TARGET and groups:
                # Find last group from this tier
                tier_groups = [g for g in groups if any(
                    e.age_category.value in tier_categories for e in g.events
                )]
                if tier_groups:
                    last_group = tier_groups[-1]
                    last_count = sum(athlete_counts.get(e.id, 0) for e in last_group.events)

                    if last_count + current_count <= MAX_TARGET:
                        idx = groups.index(last_group)
                        merged_events = last_group.events + current_group
                        groups[idx] = _make_field_group(event_type, merged_events)
                    else:
                        groups.append(_make_field_group(event_type, current_group))
                else:
                    groups.append(_make_field_group(event_type, current_group))
            else:
                groups.append(_make_field_group(event_type, current_group))

    return groups


def _make_field_group(event_type: EventType, events: list[Event]) -> EventGroup:
    """Create an EventGroup with an appropriate ID based on contained events."""
    if len(events) == 1:
        group_id = f"{event_type.value}_{events[0].age_category.value}_group"
    else:
        categories = sorted(set(e.age_category.value for e in events))
        group_id = f"{event_type.value}_{'_'.join(categories)}_group"
    return EventGroup(id=group_id, event_type=event_type, events=events)


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

        # Generate CSV for opentrack_admin
        from .csv_exporter import export_schedule_csv

        export_schedule_csv(
            result=solution,
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
