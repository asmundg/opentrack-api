"""Command-line interface for OpenTrack reports and documents."""

import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from .opentrack_utils import (
    load_opentrack_data,
    get_meeting_name,
    create_safe_filename,
    validate_events,
    get_track_event_codes,
    get_field_event_codes,
    is_track_event,
    is_field_event,
)

# Create the typer app for reports commands
app = typer.Typer(
    name="reports",
    help="Generate reports and documents from OpenTrack data",
    no_args_is_help=True,
)


@app.command("start-lists")
def start_lists(
    source: Annotated[str, typer.Argument(help="JSON source URL or local file path")],
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="Output PDF filename (optional, will be auto-generated if not provided)")] = None,
    events: Annotated[Optional[list[str]], typer.Option("--event", "-e", help="Event type code(s) to process")] = None,
    all_events: Annotated[bool, typer.Option("--all-events", help="Process all track events found in the data")] = False,
    day: Annotated[Optional[int], typer.Option("--day", "-d", help="Filter events by day number (e.g., 1, 2, 3)")] = None,
) -> None:
    """Generate start lists PDF for track events."""
    from .start_lists import create_start_lists, load_data_from_source
    
    try:
        # Load data from source
        data = load_data_from_source(source)
        
        # Validate events first - fail loudly if unrecognized events found
        print("Pre-validation of all events in dataset...")
        validate_events(data, strict_mode=True)
        print("All events recognized successfully.")
        
        # Determine which events to process
        events_to_process = None
        
        if all_events:
            # Process all track events using centralized definition
            events_to_process = []
            
            if 'events' in data:
                for event in data['events']:
                    event_code = event['eventCode']
                    if is_track_event(event_code) and event_code not in events_to_process:
                        events_to_process.append(event_code)
            
            if not events_to_process:
                print("No track events found in the data")
                raise typer.Exit(1)
        elif events:
            # Use the events specified in the arguments
            events_to_process = list(events)
        
        # Create the start lists PDF
        create_start_lists(
            data, 
            output_filename=output, 
            events=events_to_process,
            day=day
        )
        
        print("Start lists successfully generated")
        
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


@app.command("field-cards")
def field_cards(
    source: Annotated[str, typer.Argument(help="JSON source URL or local file path")],
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="Output PDF filename (optional, will be auto-generated if not provided)")] = None,
    events: Annotated[Optional[list[str]], typer.Option("--event", "-e", help="Event type code(s) to process")] = None,
    all_events: Annotated[bool, typer.Option("--all-events", help="Process all field events found in the data")] = False,
    day: Annotated[Optional[int], typer.Option("--day", "-d", help="Filter events by day number (e.g., 1, 2, 3)")] = None,
) -> None:
    """Generate field cards PDF for athletic events."""
    from .field_cards import create_field_cards, load_data_from_source
    
    try:
        # Load data from source
        data = load_data_from_source(source)
        
        # Validate events first - fail loudly if unrecognized events found
        print("Pre-validation of all events in dataset...")
        validate_events(data, strict_mode=True)
        print("All events recognized successfully.")
        
        # Determine which events to process
        events_to_process = None
        
        if all_events:
            # Process all field events using centralized definition
            events_to_process = []
            
            if 'events' in data:
                for event in data['events']:
                    event_code = event.get('eventCode', '')
                    if is_field_event(event_code) and event_code not in events_to_process:
                        events_to_process.append(event_code)
            
            if not events_to_process:
                print("No field events found in the data")
                raise typer.Exit(1)
        elif events:
            # Use the events specified in the arguments
            events_to_process = list(events)
        
        # Create the field cards PDF with automatic parameter detection
        create_field_cards(
            data, 
            output_filename=output, 
            events=events_to_process,
            day=day
        )
        
        print("Field cards successfully generated")
        
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


@app.command("competitors-by-club")
def competitors_by_club(
    source: Annotated[str, typer.Argument(help="JSON source URL or local file path")],
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="Output filename (without extension)")] = None,
    format: Annotated[str, typer.Option("--format", "-f", help="Output format: csv, pdf, or both")] = "csv",
) -> None:
    """Generate competitors list grouped by club."""
    from .competitors_by_club import (
        parse_competitors_by_club,
        save_competitors_to_csv,
    )
    from .competitors_pdf import create_pdf_from_competitors
    
    try:
        # Load data using common utility function
        json_data = load_opentrack_data(source)
        
        # Generate a filename based on the meeting name
        meeting_name = get_meeting_name(json_data)
        safe_meeting_name = create_safe_filename(meeting_name)
        
        # Base output filename without extension
        if output:
            base_output_file = output.split('.')[0]  # Remove any extension
        else:
            base_output_file = f"competitors_by_club_{safe_meeting_name}"
        
        csv_output_file = f"{base_output_file}.csv"
        pdf_output_file = f"{base_output_file}.pdf"
        
        # Parse the data
        competitors_data = parse_competitors_by_club(json_data)
        
        # Generate outputs based on format option
        if format in ["csv", "both"]:
            save_competitors_to_csv(competitors_data, csv_output_file)
        
        if format in ["pdf", "both"]:
            create_pdf_from_competitors(competitors_data, pdf_output_file, meeting_name)
                    
        # Print summary
        clubs = set(competitor['club'] for competitor in competitors_data)
        print(f"Found {len(competitors_data)} competitors from {len(clubs)} clubs")
        
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


@app.command("tyrving-csv")
def tyrving_csv(
    source: Annotated[str, typer.Argument(help="JSON source URL or local file path")],
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="Output CSV filename")] = None,
) -> None:
    """Convert OpenTrack data to Tyrving points CSV format."""
    from .opentrack_to_tyrving_csv import parse_opentrack_json, save_to_csv
    
    try:
        # Load data using utility function
        json_data = load_opentrack_data(source)
        meeting_name = get_meeting_name(json_data)
        safe_meeting_name = create_safe_filename(meeting_name)
        
        output_file = output or f"tyrvingpoeng_{safe_meeting_name}.csv"
        
        parsed_data = parse_opentrack_json(json_data)
        save_to_csv(parsed_data, output_file)
        
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
