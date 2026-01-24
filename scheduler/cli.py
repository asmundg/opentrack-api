"""Command-line interface for track meet scheduling."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from .functional_scheduler import schedule_track_meet
from .html_schedule_generator import save_html_schedule
from .csv_exporter import export_schedule_csv
from .isonen_parser import parse_isonen_csv
from .__main__ import group_events_by_type, group_events_by_date, group_athletes_by_date
from .models import Event
from . import models
from .event_csv import export_event_overview_csv, import_event_overview_csv, result_to_event_schedule_rows
from .constraint_validator import validate_event_schedule, ConstraintViolation
from .schedule_builder import build_scheduling_result_from_events

app = typer.Typer(
    name="scheduler",
    help="Track meet scheduling using constraint solving",
    no_args_is_help=True,
)


@app.command("schedule")
def schedule(
    input_file: Annotated[
        Path,
        typer.Argument(
            help="Path to the Isonen CSV file with participant data",
            exists=True,
            readable=True,
        ),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output HTML file path"),
    ] = Path("schedule.html"),
    date: Annotated[
        str | None,
        typer.Option("--date", help="Schedule only this date (YYYY-MM-DD format). If not specified, schedules all dates."),
    ] = None,
    start_hour: Annotated[
        int,
        typer.Option("--start-hour", help="Start hour (0-23)", min=0, max=23),
    ] = 17,
    start_minute: Annotated[
        int,
        typer.Option("--start-minute", help="Start minute (0-59)", min=0, max=59),
    ] = 0,
    personnel: Annotated[
        int,
        typer.Option("--personnel", "-p", help="Total personnel available", min=1),
    ] = 30,
    max_duration: Annotated[
        int | None,
        typer.Option("--max-duration", "-d", help="Maximum meet duration in minutes"),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option("--timeout", "-t", help="Solver timeout in seconds", min=1),
    ] = 10,
    title: Annotated[
        str,
        typer.Option("--title", help="Title for the HTML schedule"),
    ] = "Track Meet Schedule",
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress detailed output"),
    ] = False,
    secondary_venues: Annotated[
        bool,
        typer.Option(
            "--secondary-venues/--no-secondary-venues",
            help="Use secondary venues for young athletes (J/G10)",
        ),
    ] = True,
    max_track_duration: Annotated[
        int | None,
        typer.Option("--max-track-duration", help="Maximum track duration in minutes (track ends earlier than field)"),
    ] = None,
) -> None:
    """Generate a track meet schedule from an Isonen CSV file."""
    # Configure secondary venues
    models.USE_SECONDARY_VENUES = secondary_venues
    if not quiet:
        if secondary_venues:
            typer.echo("Secondary venues: enabled (J/G10 use separate areas)")
        else:
            typer.echo("Secondary venues: disabled")
        typer.echo(f"Parsing {input_file}...")

    events, athletes = parse_isonen_csv(str(input_file))

    if not quiet:
        typer.echo(f"Found {len(events)} events and {len(athletes)} athletes")

    # Group events by date
    events_by_date = group_events_by_date(events)
    athletes_by_date = group_athletes_by_date(athletes, events_by_date)

    # Filter to specific date if requested
    if date:
        if date not in events_by_date:
            typer.echo(f"Error: No events found for date {date}", err=True)
            available_dates = sorted(events_by_date.keys())
            typer.echo(f"Available dates: {', '.join(available_dates)}", err=True)
            raise typer.Exit(1)
        dates_to_schedule = [date]
    else:
        dates_to_schedule = sorted(events_by_date.keys())

    if not quiet:
        typer.echo(f"Found {len(dates_to_schedule)} date(s) to schedule: {', '.join(dates_to_schedule)}")

    # Schedule each date
    for schedule_date in dates_to_schedule:
        if not quiet and len(dates_to_schedule) > 1:
            typer.echo(f"\n{'='*60}")
            typer.echo(f"Scheduling {schedule_date}")
            typer.echo(f"{'='*60}")

        day_events = events_by_date[schedule_date]
        day_athletes = athletes_by_date.get(schedule_date, [])

        if not quiet:
            typer.echo(f"Date: {schedule_date}")
            typer.echo(f"Events: {len(day_events)}, Athletes: {len(day_athletes)}")

        event_groups = group_events_by_type(day_events, day_athletes)

        if not quiet:
            typer.echo(f"Created {len(event_groups)} event groups")
            typer.echo("Solving schedule...")

        # Convert max_duration to max_slots (5 min per slot)
        slot_duration = 5
        max_slots = max_duration // slot_duration if max_duration else 48

        result = schedule_track_meet(
            events=event_groups,
            athletes=day_athletes,
            total_personnel=personnel,
            max_time_slots=max_slots,
            timeout_ms=timeout * 1000,
            optimization_timeout_ms=timeout * 1000,
            max_track_duration=max_track_duration,
        )

        if result.status != "solved":
            typer.echo(f"Failed to find solution for {schedule_date}: {result.status}", err=True)
            if len(dates_to_schedule) == 1:
                raise typer.Exit(1)
            else:
                continue  # Try next date

        # Parse the date to create a proper datetime
        try:
            date_obj = datetime.strptime(schedule_date, "%Y-%m-%d")
        except ValueError:
            typer.echo(f"Warning: Could not parse date {schedule_date}, using today", err=True)
            date_obj = datetime.now()

        base_datetime = date_obj.replace(
            hour=start_hour, minute=start_minute, second=0, microsecond=0
        )

        # Validate the generated schedule as a sanity check
        if not quiet:
            typer.echo(f"\nValidating generated schedule...")
        event_schedule = result_to_event_schedule_rows(result, base_datetime, slot_duration_minutes=5)
        try:
            validate_event_schedule(
                events=event_schedule,
                event_groups=event_groups,
                athletes=day_athletes,
                slot_duration_minutes=5,
            )
        except ConstraintViolation as e:
            typer.echo(f"⚠️  Scheduler produced invalid schedule: {e}", err=True)
            # Don't fail - this is a sanity check, not a blocker

        if not quiet:
            typer.echo(f"\nSolution found!")
            typer.echo(f"Total slots: {result.total_slots}")
            typer.echo(f"Duration: {result.total_duration_minutes} minutes")

            if result.optimization_stats:
                stats = result.optimization_stats
                improvement = stats["initial_slots"] - stats["final_slots"]
                typer.echo(
                    f"Optimization: {stats['initial_slots']} -> {stats['final_slots']} slots "
                    f"(improved by {improvement})"
                )

        # Generate date-specific output filenames
        if len(dates_to_schedule) > 1:
            date_suffix = f"_{schedule_date}"
            output_html = output.parent / f"{output.stem}{date_suffix}.html"
            output_csv = output.parent / f"{output.stem}{date_suffix}.csv"
            output_events_csv = output.parent / f"{output.stem}{date_suffix}_events.csv"
            schedule_title = f"{title} - {schedule_date}"
        else:
            output_html = output
            output_csv = output.with_suffix(".csv")
            output_events_csv = output.parent / f"{output.stem}_events.csv"
            schedule_title = title

        save_html_schedule(
            result=result,
            file_path=str(output_html),
            title=schedule_title,
            start_hour=start_hour,
            start_minute=start_minute,
        )

        typer.echo(f"\nHTML schedule saved to: {output_html.absolute()}")

        # Export updated CSV with computed start times
        export_schedule_csv(
            result=result,
            original_csv_path=str(input_file),
            output_path=str(output_csv),
            start_hour=start_hour,
            start_minute=start_minute,
            base_date=base_datetime,
        )
        typer.echo(f"CSV schedule saved to: {output_csv.absolute()}")

        # Export event overview CSV for manual editing
        export_event_overview_csv(
            result=result,
            output_path=output_events_csv,
            base_date=base_datetime,
            slot_duration_minutes=5,
        )
        typer.echo(f"Event overview CSV saved to: {output_events_csv.absolute()}")

    if len(dates_to_schedule) > 1:
        typer.echo(f"\n✅ Successfully scheduled {len(dates_to_schedule)} dates")
    typer.echo(f"\n💡 Tip: You can now manually edit the _events.csv files and use")
    typer.echo(f"   'schedule from-events' to regenerate outputs with your changes.")


@app.command("info")
def info(
    input_file: Annotated[
        Path,
        typer.Argument(help="Path to the Isonen CSV file", exists=True, readable=True),
    ],
) -> None:
    """Show information about participant data without scheduling."""
    events, athletes = parse_isonen_csv(str(input_file))

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
            help="Path to the original Isonen CSV file with participant data",
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
        Path,
        typer.Option("--output", "-o", help="Output HTML file path"),
    ] = Path("schedule.html"),
    title: Annotated[
        str,
        typer.Option("--title", help="Title for the HTML schedule"),
    ] = "Track Meet Schedule",
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress detailed output"),
    ] = False,
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
    if not quiet:
        typer.echo(f"Parsing participant data from {input_file}...")

    # Parse original data to get event groups and athletes
    events, athletes = parse_isonen_csv(str(input_file))
    event_groups = group_events_by_type(events, athletes)

    if not quiet:
        typer.echo(f"Found {len(events)} events and {len(athletes)} athletes")
        typer.echo(f"Created {len(event_groups)} event groups")
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
            events=event_schedule,
            event_groups=event_groups,
            athletes=athletes,
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
        events=event_schedule,
        event_groups=event_groups,
        athletes=athletes,
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

    # Export updated athlete CSV with manual times
    csv_output = output.with_suffix(".csv")
    export_schedule_csv(
        result=result,
        original_csv_path=str(input_file),
        output_path=str(csv_output),
        start_hour=earliest_time.hour,
        start_minute=earliest_time.minute,
    )
    typer.echo(f"CSV schedule saved to: {csv_output.absolute()}")


if __name__ == "__main__":
    app()
