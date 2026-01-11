"""Command-line interface for track meet scheduling."""

from pathlib import Path
from typing import Annotated

import typer

from .functional_scheduler import schedule_track_meet
from .html_schedule_generator import save_html_schedule
from .isonen_parser import parse_isonen_csv
from .__main__ import group_events_by_type
from .models import Event

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
) -> None:
    """Generate a track meet schedule from an Isonen CSV file."""
    if not quiet:
        typer.echo(f"Parsing {input_file}...")

    events, athletes = parse_isonen_csv(str(input_file))

    if not quiet:
        typer.echo(f"Found {len(events)} events and {len(athletes)} athletes")

    event_groups = group_events_by_type(events, athletes)

    if not quiet:
        typer.echo(f"Created {len(event_groups)} event groups")
        typer.echo("Solving schedule...")

    # Convert max_duration to max_slots (5 min per slot)
    slot_duration = 5
    max_slots = max_duration // slot_duration if max_duration else 48

    result = schedule_track_meet(
        events=event_groups,
        athletes=athletes,
        total_personnel=personnel,
        max_time_slots=max_slots,
        timeout_ms=timeout * 1000,
        optimization_timeout_ms=timeout * 1000,
    )

    if result.status != "solved":
        typer.echo(f"Failed to find solution: {result.status}", err=True)
        raise typer.Exit(1)

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

    save_html_schedule(
        result=result,
        file_path=str(output),
        title=title,
        start_hour=start_hour,
        start_minute=start_minute,
    )

    typer.echo(f"\nHTML schedule saved to: {output.absolute()}")


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


if __name__ == "__main__":
    app()
