"""Command-line interface for track meet scheduling."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from .html_schedule_generator import save_html_schedule
from .isonen_parser import parse_isonen_xlsx
from .models import Event, EventType
from . import models
from .event_csv import import_event_overview_csv
from .constraint_validator import validate_event_schedule, ConstraintViolation
from .schedule_builder import build_scheduling_result_from_events
from .hurdle_plan_generator import generate_hurdle_plan_html

app = typer.Typer(
    name="scheduler",
    help="Track meet scheduling using constraint solving",
    no_args_is_help=True,
)


def _parse_shared_venue_groups(shared: list[str]) -> list[frozenset[EventType]]:
    """Parse repeated --shared values into a list of EventType groups.

    Each value is a comma-separated list of EventType enum names (e.g. "jt,dt,ht").
    Validates that every name resolves, that each group has at least 2 members,
    and that no event type appears in more than one group.
    """
    groups: list[frozenset[EventType]] = []
    seen: dict[EventType, str] = {}
    for raw in shared:
        names = [n.strip() for n in raw.split(",") if n.strip()]
        if len(names) < 2:
            typer.echo(
                f"--shared group needs at least two event types: '{raw}'", err=True
            )
            raise typer.Exit(1)
        types: list[EventType] = []
        for name in names:
            try:
                et = EventType[name]
            except KeyError:
                valid = ", ".join(e.name for e in EventType)
                typer.echo(
                    f"Unknown event type '{name}' in --shared. Valid: {valid}",
                    err=True,
                )
                raise typer.Exit(1)
            if et in seen:
                typer.echo(
                    f"Event type '{name}' appears in multiple --shared groups "
                    f"(also in '{seen[et]}')",
                    err=True,
                )
                raise typer.Exit(1)
            seen[et] = raw
            types.append(et)
        groups.append(frozenset(types))
    return groups


def _echo_shared_groups(quiet: bool) -> None:
    if quiet or not models.SHARED_VENUE_GROUPS:
        return
    descriptions = [
        ",".join(sorted(et.name for et in group))
        for group in models.SHARED_VENUE_GROUPS
    ]
    typer.echo(f"Shared venue groups: {'; '.join(descriptions)}")


@app.command("info")
def info(
    input_file: Annotated[
        Path,
        typer.Argument(help="Path to the Isonen XLSX file", exists=True, readable=True),
    ],
    date: Annotated[
        str | None,
        typer.Option("--date", help="Only show events on this date (DD.MM.YYYY format)"),
    ] = None,
) -> None:
    """Show information about participant data without scheduling."""
    events, athletes = parse_isonen_xlsx(str(input_file), filter_date=date)

    typer.echo(f"Events: {len(events)}")
    typer.echo(f"Athletes: {len(athletes)}")

    typer.echo("\nEvents by type:")
    event_types: dict[str, list[Event]] = {}
    for event in events:
        et = event.event_type.value
        if et not in event_types:
            event_types[et] = []
        event_types[et].append(event)

    for et, events_of_type in sorted(event_types.items()):
        typer.echo(f"  {et}: {len(events_of_type)} categories")
        for event in events_of_type:
            typer.echo(f"    - {event.age_category.value} ({event.duration_minutes}min)")

    typer.echo(f"\nSample athletes (first 5):")
    for athlete in athletes[:5]:
        event_names = [f"{e.event_type.value} {e.age_category.value}" for e in athlete.events]
        typer.echo(f"  {athlete.name}: {', '.join(event_names)}")

    if len(athletes) > 5:
        typer.echo(f"  ... and {len(athletes) - 5} more")


@app.command("from-events")
def schedule_from_events(
    input_file: Annotated[
        Path,
        typer.Argument(
            help="Path to the original Isonen XLSX file with participant data",
            exists=True,
            readable=True,
        ),
    ],
    events_csv: Annotated[
        Path,
        typer.Argument(
            help="Path to the event overview CSV with manual timings",
            exists=True,
            readable=True,
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output", "-o",
            help="Output HTML file path. Defaults to the events CSV name with "
                 "the '_events.csv' suffix replaced by '.html' (e.g. "
                 "'schedule_2026-05-20_events.csv' -> 'schedule_2026-05-20.html').",
        ),
    ] = None,
    title: Annotated[
        str,
        typer.Option("--title", help="Title for the HTML schedule"),
    ] = "Track Meet Schedule",
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress detailed output"),
    ] = False,
    arena: Annotated[
        str,
        typer.Option("--arena", help="Arena name (e.g. 'tromsohallen') for venue-specific lane limits and markers"),
    ] = "generic",
    date: Annotated[
        str | None,
        typer.Option("--date", help="Only include events on this date (DD.MM.YYYY format)"),
    ] = None,
    shared: Annotated[
        list[str] | None,
        typer.Option(
            "--shared",
            help="Comma-separated event types that share a venue/officials and cannot "
                 "run in parallel (e.g. 'jt,dt,ht'). Repeat for multiple groups. "
                 "Must match what was used for the original schedule.",
        ),
    ] = None,
    sticky: Annotated[
        bool,
        typer.Option(
            "--sticky/--no-sticky",
            help="Validate that event types form contiguous blocks per venue. "
                 "Pass the same value used for the original schedule.",
        ),
    ] = True,
) -> None:
    """
    Generate outputs from manually edited event overview CSV.

    This command:
    1. Reads the event overview CSV with manual event times
    2. Validates that all constraints are still satisfied
    3. Generates updated HTML schedule and athlete CSV

    This workflow allows manual adjustments between automated scheduling
    and final output generation.
    """
    # Configure arena
    if arena not in models.ARENAS:
        typer.echo(f"Unknown arena: '{arena}'. Available: {', '.join(models.ARENAS)}", err=True)
        raise typer.Exit(1)
    models.ARENA = models.ARENAS[arena]
    models.ACTIVE_SECONDARY_VENUES = {
        EventType[name] for name in models.ARENA.default_secondary_venues
    }
    models.SHARED_VENUE_GROUPS = _parse_shared_venue_groups(shared or [])
    models.STICKY_VENUES = sticky
    _echo_shared_groups(quiet)
    if not quiet and models.STICKY_VENUES:
        typer.echo("Sticky venues: ON")

    # Derive default output from the events CSV (which encodes the date).
    if output is None:
        stem = events_csv.stem
        if stem.endswith("_events"):
            stem = stem[: -len("_events")]
        output = events_csv.parent / f"{stem}.html"

    # Inject date into output filename
    if date:
        parts = date.split(".")
        date_slug = f"{parts[2]}-{parts[1]}-{parts[0]}"
        output = output.parent / f"{output.stem}_{date_slug}{output.suffix}"

    if not quiet:
        typer.echo(f"Parsing participant data from {input_file}...")

    # Parse original data to get raw event atoms and athletes. Merging is the
    # layout's job (the CSV); we do NOT re-derive groups here.
    events, athletes = parse_isonen_xlsx(str(input_file), filter_date=date)

    if not quiet:
        if date:
            typer.echo(f"Filtering to events on {date}")
        typer.echo(f"Found {len(events)} events and {len(athletes)} athletes")
        typer.echo(f"\nImporting event schedule from {events_csv}...")

    # Import event overview CSV
    try:
        event_schedule = import_event_overview_csv(events_csv)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Error reading event CSV: {e}", err=True)
        raise typer.Exit(1)

    if not quiet:
        typer.echo(f"Validating constraints...")

    # Validate constraints
    try:
        validate_event_schedule(
            event_schedule,
            events,
            athletes,
            slot_duration_minutes=5,
        )
    except ConstraintViolation as e:
        typer.echo(f"\n❌ Constraint violation detected:", err=True)
        typer.echo(f"   {e}", err=True)
        typer.echo(f"\nPlease fix the constraint violations in {events_csv} and try again.", err=True)
        raise typer.Exit(1)

    if not quiet:
        typer.echo(f"Building schedule from manual event times...")

    # Derive base time from earliest event in the CSV
    earliest_time = min(e.start_time for e in event_schedule)
    base_datetime = datetime.now().replace(
        hour=earliest_time.hour, minute=earliest_time.minute, second=0, microsecond=0
    )

    result = build_scheduling_result_from_events(
        event_schedule,
        events,
        athletes,
        base_date=base_datetime,
        slot_duration_minutes=5,
    )

    if not quiet:
        typer.echo(f"\nSchedule built successfully!")
        typer.echo(f"Total slots: {result.total_slots}")
        typer.echo(f"Duration: {result.total_duration_minutes} minutes")

    # Generate HTML schedule
    save_html_schedule(
        result=result,
        file_path=str(output),
        title=title,
        start_hour=earliest_time.hour,
        start_minute=earliest_time.minute,
    )

    typer.echo(f"\nHTML schedule saved to: {output.absolute()}")

    # Generate hurdle setup plan if there are hurdle events
    hurdle_html = generate_hurdle_plan_html(result, earliest_time.hour, earliest_time.minute)
    if hurdle_html:
        hurdle_output = output.parent / f"{output.stem}_hurdles.html"
        hurdle_output.write_text(hurdle_html)
        typer.echo(f"Hurdle plan saved to: {hurdle_output.absolute()}")


if __name__ == "__main__":
    app()
