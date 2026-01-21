"""Command-line interface for OpenTrack automation."""

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from .browser import OpenTrackSession
from .competition import CompetitionCreator, CompetitionDetails
from .config import OpenTrackConfig
from .events import EventSchedule, EventScheduler, parse_schedule_csv, Checkpoint
from pblookup import PBLookupService

# Create the typer app for admin commands
app = typer.Typer(
    name="admin",
    help="OpenTrack event administration automation",
    no_args_is_help=True,
)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command("test-login")
def test_login() -> None:
    """Test login to OpenTrack."""
    config = OpenTrackConfig.from_env()
    
    if not config.username or not config.password:
        print("❌ Error: OPENTRACK_USERNAME and OPENTRACK_PASSWORD must be set")
        print()
        print("Create a .env file with:")
        print("  OPENTRACK_USERNAME=your_username")
        print("  OPENTRACK_PASSWORD=your_password")
        raise typer.Exit(1)

    print(f"🔐 Testing login to {config.base_url}...")
    
    with OpenTrackSession(config) as session:
        session.goto_home()
        session.login()
        
        if session.is_logged_in():
            print("✅ Login successful!")
        else:
            print("❌ Login failed - check credentials")
            raise typer.Exit(1)


@app.command()
def create(
    name: Annotated[str, typer.Argument(help="Full competition name (e.g., 'Seriestevne 9-2025')")],
    slug: Annotated[str, typer.Argument(help="URL slug (e.g., 'ser9-25')")],
    start_date: Annotated[str, typer.Argument(help="Start date (YYYY-MM-DD)", metavar="DATE")],
    contact_email: Annotated[str, typer.Argument(help="Contact email for the competition")],
    organiser: Annotated[str, typer.Argument(help="Organiser search term (e.g., 'BULTF')")],
    end_date: Annotated[Optional[str], typer.Option("--end-date", help="End date if multi-day (YYYY-MM-DD)")] = None,
    short_name: Annotated[Optional[str], typer.Option("--short-name", help="Short name (optional)")] = None,
    competition_type: Annotated[str, typer.Option("--type", help="Competition type (track, indoor, road, cross_country, trail)")] = "track",
    website: Annotated[Optional[str], typer.Option("--website", help="Competition/club website URL")] = None,
    entry_link: Annotated[Optional[str], typer.Option("--entry-link", help="External entry link (e.g., Isonen URL)")] = None,
    public: Annotated[bool, typer.Option("--public", help="Make competition public immediately (default: hidden)")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose/debug logging")] = False,
) -> None:
    """Create a new competition."""
    setup_logging(verbose=verbose)

    config = OpenTrackConfig.from_env()
    
    if not config.username or not config.password:
        print("❌ Error: OPENTRACK_USERNAME and OPENTRACK_PASSWORD must be set")
        raise typer.Exit(1)

    # Parse date
    try:
        parsed_start_date = date.fromisoformat(start_date)
    except ValueError:
        print(f"❌ Invalid date format: {start_date}")
        print("   Use YYYY-MM-DD format")
        raise typer.Exit(1)

    parsed_end_date = None
    if end_date:
        try:
            parsed_end_date = date.fromisoformat(end_date)
        except ValueError:
            print(f"❌ Invalid end date format: {end_date}")
            raise typer.Exit(1)

    details = CompetitionDetails(
        name=name,
        slug=slug,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
        contact_email=contact_email,
        organiser_search=organiser,
        short_name=short_name or "",
        competition_type=competition_type,
        website=website or "",
        external_entry_link=entry_link or "",
        hide_from_public=not public,
        combined_events_table="tyrving",
    )

    print(f"🏃 Creating competition: {details.name}")
    print(f"   Slug: {details.slug}")
    print(f"   Date: {details.start_date}")
    print(f"   Type: {details.competition_type}")
    print(f"   Organiser: {details.organiser_search}")
    print()
    
    with OpenTrackSession(config) as session:
        session.goto_home()
        creator = CompetitionCreator(session)
        
        try:
            url = creator.create_competition(details)
            print(f"✅ Competition created: {url}")
        except Exception as e:
            print(f"❌ Error creating competition: {e}")
            raise typer.Exit(1)


@app.command()
def schedule(
    competition_url: Annotated[str, typer.Argument(help="URL of the competition (e.g., https://norway.opentrack.run/x/2025/NOR/ser9-25/)")],
    file: Annotated[Path, typer.Argument(help="Isonen-format schedule CSV (schedule.csv from scheduler)")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose/debug logging")] = False,
    no_checkpoint: Annotated[bool, typer.Option("--no-checkpoint", help="Disable checkpoint (re-process all events even if previously done)")] = False,
) -> None:
    """Schedule events (set start times) for a competition."""
    setup_logging(verbose=verbose)
    logger = logging.getLogger(__name__)
    
    config = OpenTrackConfig.from_env()
    
    if not config.username or not config.password:
        print("❌ Error: OPENTRACK_USERNAME and OPENTRACK_PASSWORD must be set")
        raise typer.Exit(1)

    if not file.exists():
        print(f"❌ Schedule file not found: {file}")
        raise typer.Exit(1)
    
    schedules = parse_schedule_csv(file.read_text())
    
    if not schedules:
        print("❌ No valid events found in schedule file.")
        print("   Expected CSV format: category,event,start_time")
        raise typer.Exit(1)

    print(f"📅 Scheduling {len(schedules)} events...")
    for s in schedules:
        print(f"   {s.category} {s.event} @ {s.start_time.strftime('%H:%M')}")
    print()
    
    # Extract checkpoint name from competition URL (use slug)
    # e.g., https://norway.opentrack.run/x/2025/NOR/ser9-25/ -> ser9-25
    checkpoint_name = competition_url.rstrip("/").split("/")[-1] if not no_checkpoint else None
    if checkpoint_name:
        print(f"📍 Using checkpoint: {checkpoint_name}")
    
    with OpenTrackSession(config) as session:
        # Navigate to competition
        session.page.goto(competition_url)
        session.page.wait_for_load_state("networkidle")
        
        # Ensure logged in
        if not session.is_logged_in():
            session.login()
            session.page.goto(competition_url)
            session.page.wait_for_load_state("networkidle")
        
        scheduler = EventScheduler(session)
        
        try:
            scheduler.schedule_events(schedules, checkpoint_name=checkpoint_name)
            print()
            print(f"✅ All {len(schedules)} events scheduled successfully!")
        except Exception as e:
            print()
            print(f"❌ Failed: {e}")
            raise typer.Exit(1)


@app.command("update-pbs")
def update_pbs(
    competition_url: Annotated[str, typer.Argument(help="URL of the competition (e.g., https://norway.opentrack.run/x/2025/NOR/ser9-25/)")],
    file: Annotated[Optional[Path], typer.Argument(help="Isonen-format schedule CSV (schedule.csv from scheduler)")] = None,
    event: Annotated[Optional[str], typer.Option("--event", "-e", help="Single event code (e.g., 'LJ', 'SP', '100m')")] = None,
    category: Annotated[Optional[str], typer.Option("--category", "-c", help="Single event category (e.g., 'G14', 'J15')")] = None,
    club: Annotated[str, typer.Option("--club", help="Default club name for PB lookups (e.g., 'Tyrving')")] = "",
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose/debug logging")] = False,
    debug_pblookup: Annotated[bool, typer.Option("--debug-pblookup", help="Enable debug output from pblookup service")] = False,
    no_checkpoint: Annotated[bool, typer.Option("--no-checkpoint", help="Disable checkpoint (re-process all events even if previously done)")] = False,
) -> None:
    """Update PB/SB values for competitors in events.

    Either provide a CSV file with all events, or use --event and --category for a single event.
    """
    setup_logging(verbose=verbose)
    logger = logging.getLogger(__name__)

    config = OpenTrackConfig.from_env()

    if not config.username or not config.password:
        print("❌ Error: OPENTRACK_USERNAME and OPENTRACK_PASSWORD must be set")
        raise typer.Exit(1)

    # Build schedule list from file or single event
    if event and category:
        # Single event mode
        from datetime import time as dt_time
        schedules = [EventSchedule(category=category, event=event, start_time=dt_time(0, 0))]
        print(f"📊 Updating PBs for single event: {category} {event}")
    elif file:
        if not file.exists():
            print(f"❌ Schedule file not found: {file}")
            raise typer.Exit(1)

        schedules = parse_schedule_csv(file.read_text())

        if not schedules:
            print("❌ No valid events found in schedule file.")
            print("   Expected CSV format: category,event,start_time")
            raise typer.Exit(1)

        print(f"📊 Updating PBs for {len(schedules)} events...")
    else:
        print("❌ Either provide a CSV file or use --event and --category")
        raise typer.Exit(1)
    if club:
        print(f"   Default club: {club}")
    print()
    
    # Extract checkpoint name from competition URL (use slug with -pbs suffix)
    checkpoint_name = None
    if not no_checkpoint:
        slug = competition_url.rstrip("/").split("/")[-1]
        checkpoint_name = f"{slug}-pbs"
        print(f"📍 Using checkpoint: {checkpoint_name}")
    
    checkpoint = Checkpoint(checkpoint_name) if checkpoint_name else None
    
    # Count how many we'll skip
    if checkpoint:
        skip_count = sum(1 for s in schedules if checkpoint.is_done(s.search_term))
        if skip_count > 0:
            print(f"   Skipping {skip_count} already-completed events")
    
    with OpenTrackSession(config) as session:
        # Navigate to competition
        session.page.goto(competition_url)
        session.page.wait_for_load_state("networkidle")
        
        # Ensure logged in
        if not session.is_logged_in():
            session.login()
            session.page.goto(competition_url)
            session.page.wait_for_load_state("networkidle")
        
        scheduler = EventScheduler(session)
        scheduler.navigate_to_events_table()
        
        total_updated = 0
        errors = []
        
        for i, sched in enumerate(schedules, 1):
            # Skip FIFA category (not defined in OpenTrack)
            if sched.category.upper() == "FIFA":
                logger.info(f"Skipping {i}/{len(schedules)}: {sched.search_term} (FIFA category)")
                continue
            
            # Skip if already done
            if checkpoint and checkpoint.is_done(sched.search_term):
                print(f"⏭️  Skipping {i}/{len(schedules)}: {sched.search_term} (already done)")
                continue
            
            print(f"🔍 Processing {i}/{len(schedules)}: {sched.search_term}")
            
            try:
                # Find and click the event
                scheduler.find_and_click_event(sched)
                
                # Update PBs
                updated = scheduler.update_event_pbs(
                    schedule=sched,
                    default_club=club,
                    debug=debug_pblookup,
                )
                total_updated += updated
                print(f"   ✅ Updated {updated} competitors")
                
                # Mark as done in checkpoint
                if checkpoint:
                    checkpoint.mark_done(sched.search_term)
                
                # Navigate back to events table for next event
                scheduler.navigate_to_events_table()
                
            except Exception as e:
                logger.error(f"Error processing {sched.search_term}: {e}")
                errors.append((sched.search_term, str(e)))
                # Try to recover by navigating back to events table
                try:
                    scheduler.navigate_to_events_table()
                except Exception:
                    pass
        
        print()
        print(f"✅ Updated PBs for {total_updated} total competitors")
        
        if errors:
            print()
            print(f"⚠️  {len(errors)} events had errors:")
            for event, error in errors:
                print(f"   - {event}: {error}")
            raise typer.Exit(1)


@app.command("lookup-pb")
def lookup_pb(
    name: Annotated[str, typer.Argument(help="Athlete's full name")],
    club: Annotated[str, typer.Option("--club", "-c", help="Club name for disambiguation")] = "",
    birth_date: Annotated[str, typer.Option("--birth", "-b", help="Birth date (DD.MM.YYYY) for disambiguation")] = "",
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Enable debug output")] = False,
) -> None:
    """Look up PBs for an athlete by name."""
    service = PBLookupService(debug=debug)

    print(f"🔍 Looking up: {name}")
    if club:
        print(f"   Club: {club}")
    if birth_date:
        print(f"   Birth: {birth_date}")
    print()

    athlete = service.lookup_athlete(name, club=club, birth_date=birth_date)

    if not athlete:
        print("❌ No athlete found")
        raise typer.Exit(1)

    print(f"✅ Found: {athlete.name}")
    if athlete.birth_date:
        print(f"   Birth: {athlete.birth_date}")
    if athlete.clubs:
        print(f"   Clubs: {', '.join(athlete.clubs)}")
    print()

    if athlete.outdoor_pbs:
        print("Outdoor PBs:")
        for event, result in sorted(athlete.outdoor_pbs.items()):
            print(f"   {event}: {result}")

    if athlete.indoor_pbs:
        print("\nIndoor PBs:")
        for event, result in sorted(athlete.indoor_pbs.items()):
            print(f"   {event}: {result}")

    if not athlete.outdoor_pbs and not athlete.indoor_pbs:
        print("   No PBs found")


# Legacy entry point for backwards compatibility
def main() -> int:
    """Legacy entry point - redirects to typer app."""
    app()
    return 0


if __name__ == "__main__":
    app()
