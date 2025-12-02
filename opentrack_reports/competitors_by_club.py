#!/usr/bin/env python3
# filepath: /Volumes/src/priv/opentrack/competitors_by_club.py
import csv
import sys
from collections import defaultdict
from typing import Any

from .competitors_pdf import create_pdf_from_competitors
from .opentrack_utils import (
    clean_event_name,
    create_safe_filename,
    get_meeting_name,
    load_opentrack_data,
)


def parse_competitors_by_club(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse OpenTrack JSON and create a list of competitors by club with their events."""

    # First pass: collect all unique team names for each teamId to handle unicode duplicates
    team_names_by_id = {}
    for competitor in data["competitors"]:
        team_id = competitor["teamId"]
        team_name = competitor["teamName"]

        if team_id not in team_names_by_id:
            team_names_by_id[team_id] = set()
        team_names_by_id[team_id].add(team_name)

    # Create mapping from teamId to preferred team name (prefer unicode over ASCII)
    def prefer_unicode_name(names: set[str]) -> str:
        """Choose unicode version over ASCII version of team names."""
        if len(names) == 1:
            return list(names)[0]

        # Sort by unicode content - names with more unicode chars come first
        sorted_names = sorted(names, key=lambda x: -sum(1 for c in x if ord(c) > 127))
        return sorted_names[0]

    preferred_team_names = {
        team_id: prefer_unicode_name(names)
        for team_id, names in team_names_by_id.items()
    }

    # Build a dictionary of competitors by bib number
    competitors = {}

    for competitor in data["competitors"]:
        # Require fields instead of using .get() with fallbacks
        first_name = competitor["firstName"]
        last_name = competitor["lastName"]
        name = f"{first_name} {last_name}".strip()

        # Get preferred club name using teamId
        team_id = competitor["teamId"]
        club = preferred_team_names[team_id]
        category = competitor["category"]

        # Extract PB and SB per event from eventsEntered
        pb_by_event = {}
        sb_by_event = {}
        for event_entry in competitor.get("eventsEntered", []):
            event_id = event_entry.get("eventId", "")
            if event_id:
                pb_by_event[event_id] = event_entry.get("pb", "")
                sb_by_event[event_id] = event_entry.get("sb", "")

        # Use sortBib as the key for the competitor dictionary if available
        if "sortBib" in competitor:
            bib = competitor["sortBib"].lstrip("0")  # Remove leading zeros
            competitors[bib] = {
                "name": name,
                "club": club,
                "category": category,
                "bib": bib,
                "events": set(),  # Use set to avoid duplicates
                "pb_by_event": pb_by_event,
                "sb_by_event": sb_by_event,
            }

    # Process events to find which competitors are in which events
    for event in data["events"]:
        event_name = event["name"]
        clean_name = clean_event_name(event_name)

        # Process units within events
        for unit in event["units"]:
            # Process results within units
            for result in unit["results"]:
                bib = result["bib"]
                if bib in competitors:
                    competitors[bib]["events"].add(clean_name)

    # Convert sets to sorted lists and group by club
    club_competitors = defaultdict(list)

    for bib, competitor_info in competitors.items():
        # Convert events set to sorted list
        competitor_info["events"] = sorted(list(competitor_info["events"]))
        club_competitors[competitor_info["club"]].append(competitor_info)

    # Sort competitors within each club by bib number
    for club in club_competitors:
        club_competitors[club].sort(
            key=lambda x: int(x["bib"]) if x["bib"].isdigit() else float("inf")
        )

    # Convert to list and sort by club name
    result = []
    for club in sorted(club_competitors.keys()):
        result.extend(club_competitors[club])

    return result


def save_competitors_to_csv(
    data: list[dict[str, Any]], filename: str = "competitors_by_club.csv"
) -> None:
    """Save competitors data to CSV."""
    fieldnames = ["Klubb", "Startnummer", "Navn", "Klasse", "Øvelser"]

    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for competitor in data:
            # Join events with semicolon separator
            events_str = "; ".join(competitor["events"]) if competitor["events"] else ""

            writer.writerow(
                {
                    "Klubb": competitor["club"],
                    "Startnummer": competitor["bib"],
                    "Navn": competitor["name"],
                    "Klasse": competitor["category"],
                    "Øvelser": events_str,
                }
            )

    print(f"Competitors data saved to {filename}")


def print_usage() -> None:
    """Print usage information for the script."""
    print(
        "Usage: python3 competitors_by_club.py <url_or_file> [options] [output_base_filename]"
    )
    print("\nArguments:")
    print(
        "  url_or_file             URL to OpenTrack competition or local JSON file path"
    )
    print("  output_base_filename    Base filename for output (without extension)")
    print("\nOptions:")
    print("  --csv                   Generate CSV output only (default)")
    print("  --pdf                   Generate PDF output only")
    print("  --both                  Generate both CSV and PDF outputs")
    print("\nExamples:")
    print("  python3 competitors_by_club.py https://data.opentrack.run/x/2023/NOR/ntm/")
    print("  python3 competitors_by_club.py local_data.json --pdf")
    print(
        "  python3 competitors_by_club.py https://data.opentrack.run/x/2023/NOR/ntm/ --both custom_output"
    )
    print("  python3 competitors_by_club.py local_data.json custom_output --csv")


def main() -> None:
    # Check if argument is provided
    if len(sys.argv) <= 1:
        print_usage()
        sys.exit(1)

    # Check for help flag
    if "--help" in sys.argv or "-h" in sys.argv:
        print_usage()
        sys.exit(0)

    input_source = sys.argv[1]
    format_option = "csv"  # Default format is CSV

    # Check for format option
    for arg in sys.argv[1:]:
        if arg.lower() in ["--csv", "--pdf", "--both"]:
            format_option = arg.lower().replace("--", "")
            break

    try:
        # Load data using common utility function
        json_data = load_opentrack_data(input_source)

        # Generate a filename based on the meeting name
        meeting_name = get_meeting_name(json_data)
        safe_meeting_name = create_safe_filename(meeting_name)

        # Base output filename without extension
        base_output_file = f"competitors_by_club_{safe_meeting_name}"
        csv_output_file = f"{base_output_file}.csv"
        pdf_output_file = f"{base_output_file}.pdf"

        # Override with command line argument if provided
        for arg in sys.argv[2:]:
            if not arg.startswith("--"):
                # This is likely a filename specification
                base_output_file = arg.split(".")[0]  # Remove any extension
                csv_output_file = f"{base_output_file}.csv"
                pdf_output_file = f"{base_output_file}.pdf"
                break

        # Parse the data
        competitors_data = parse_competitors_by_club(json_data)

        # Generate outputs based on format option
        if format_option in ["csv", "both"]:
            save_competitors_to_csv(competitors_data, csv_output_file)

        if format_option in ["pdf", "both"]:
            create_pdf_from_competitors(competitors_data, pdf_output_file, meeting_name)

        # Print summary
        clubs = set(competitor["club"] for competitor in competitors_data)
        print(f"Found {len(competitors_data)} competitors from {len(clubs)} clubs")

    except Exception as e:
        sys.exit(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
