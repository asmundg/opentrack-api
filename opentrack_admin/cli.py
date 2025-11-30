"""Command-line interface for OpenTrack automation."""

import argparse
import logging
import subprocess
import sys
from datetime import date
from pathlib import Path

from .browser import OpenTrackSession
from .competition import CompetitionCreator, CompetitionDetails
from .config import OpenTrackConfig, RECORDINGS_DIR
from .events import EventScheduler, parse_schedule_csv


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_record(args: argparse.Namespace) -> int:
    """Launch Playwright codegen to record interactions."""
    config = OpenTrackConfig.from_env()
    
    print("🎬 Launching Playwright recorder...")
    print(f"   Target: {config.base_url}")
    print()
    print("Instructions:")
    print("  1. Log in to OpenTrack")
    print("  2. Navigate through the competition creation flow")
    print("  3. The recorder will generate Python code for each action")
    print("  4. Copy the generated code to update competition.py")
    print()
    
    # Ensure recordings directory exists
    RECORDINGS_DIR.mkdir(exist_ok=True)
    
    # Launch codegen
    cmd = [
        sys.executable, "-m", "playwright", "codegen",
        config.base_url,
        "--target", "python",
        "-o", str(RECORDINGS_DIR / "recorded_flow.py"),
    ]
    
    return subprocess.call(cmd)


def cmd_test_login(args: argparse.Namespace) -> int:
    """Test login to OpenTrack."""
    config = OpenTrackConfig.from_env()
    
    if not config.username or not config.password:
        print("❌ Error: OPENTRACK_USERNAME and OPENTRACK_PASSWORD must be set")
        print()
        print("Create a .env file with:")
        print("  OPENTRACK_USERNAME=your_username")
        print("  OPENTRACK_PASSWORD=your_password")
        return 1

    print(f"🔐 Testing login to {config.base_url}...")
    
    with OpenTrackSession(config) as session:
        session.goto_home()
        session.login()
        
        if session.is_logged_in():
            print("✅ Login successful!")
            return 0
        else:
            print("❌ Login failed - check credentials")
            return 1


def cmd_create_competition(args: argparse.Namespace) -> int:
    """Create a new competition."""
    config = OpenTrackConfig.from_env()
    
    if not config.username or not config.password:
        print("❌ Error: OPENTRACK_USERNAME and OPENTRACK_PASSWORD must be set")
        return 1

    # Parse date
    try:
        start_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"❌ Invalid date format: {args.date}")
        print("   Use YYYY-MM-DD format")
        return 1

    end_date = None
    if args.end_date:
        try:
            end_date = date.fromisoformat(args.end_date)
        except ValueError:
            print(f"❌ Invalid end date format: {args.end_date}")
            return 1

    details = CompetitionDetails(
        name=args.name,
        slug=args.slug,
        start_date=start_date,
        end_date=end_date,
        contact_email=args.contact_email,
        organiser_search=args.organiser,
        short_name=args.short_name or "",
        competition_type=args.type,
        website=args.website or "",
        external_entry_link=args.entry_link or "",
        hide_from_public=not args.public,
        show_individual_points=args.show_points,
        combined_events_table="tyrving" if args.tyrving_scoring else None,
        auto_number_competitors=args.number_competitors,
        random_seeding=args.random_seeding,
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
            return 0
        except Exception as e:
            print(f"❌ Error creating competition: {e}")
            return 1


def cmd_schedule_events(args: argparse.Namespace) -> int:
    """Schedule events for a competition."""
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)
    
    config = OpenTrackConfig.from_env()
    
    if not config.username or not config.password:
        print("❌ Error: OPENTRACK_USERNAME and OPENTRACK_PASSWORD must be set")
        return 1

    # Collect schedules from CSV file
    if not args.file:
        print("❌ Schedule file required. Use --file or -f.")
        return 1
    
    schedule_path = Path(args.file)
    if not schedule_path.exists():
        print(f"❌ Schedule file not found: {args.file}")
        return 1
    
    schedules = parse_schedule_csv(schedule_path.read_text())
    
    if not schedules:
        print("❌ No valid events found in schedule file.")
        print("   Expected CSV format: category,event,start_time")
        return 1

    print(f"📅 Scheduling {len(schedules)} events...")
    for s in schedules:
        print(f"   {s.category} {s.event} @ {s.start_time.strftime('%H:%M')}")
    print()
    
    with OpenTrackSession(config) as session:
        # Navigate to competition
        session.page.goto(args.competition_url)
        session.page.wait_for_load_state("networkidle")
        
        # Ensure logged in
        if not session.is_logged_in():
            session.login()
            session.page.goto(args.competition_url)
            session.page.wait_for_load_state("networkidle")
        
        scheduler = EventScheduler(session)
        results = scheduler.schedule_events(schedules)
        
        # Report results
        success_count = sum(1 for v in results.values() if v)
        fail_count = len(results) - success_count
        
        print()
        if fail_count == 0:
            print(f"✅ All {success_count} events scheduled successfully!")
        else:
            print(f"⚠️  {success_count} events scheduled, {fail_count} failed:")
            for term, success in results.items():
                if not success:
                    print(f"   ❌ {term}")
        
        return 0 if fail_count == 0 else 1


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="opentrack",
        description="OpenTrack event administration automation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Record command
    record_parser = subparsers.add_parser(
        "record",
        help="Launch Playwright recorder to capture interactions",
    )
    record_parser.set_defaults(func=cmd_record)

    # Test login command
    login_parser = subparsers.add_parser(
        "test-login",
        help="Test login to OpenTrack",
    )
    login_parser.set_defaults(func=cmd_test_login)

    # Create competition command
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new competition",
    )
    create_parser.add_argument("name", help="Full competition name (e.g., 'Seriestevne 9-2025')")
    create_parser.add_argument("slug", help="URL slug (e.g., 'ser9-25')")
    create_parser.add_argument("date", help="Start date (YYYY-MM-DD)")
    create_parser.add_argument("contact_email", help="Contact email for the competition")
    create_parser.add_argument("organiser", help="Organiser search term (e.g., 'BULTF')")
    create_parser.add_argument("--end-date", help="End date if multi-day (YYYY-MM-DD)")
    create_parser.add_argument("--short-name", help="Short name (optional)")
    create_parser.add_argument(
        "--type",
        choices=["track", "indoor", "road", "cross_country", "trail"],
        default="track",
        help="Competition type (default: track)",
    )
    create_parser.add_argument("--website", help="Competition/club website URL")
    create_parser.add_argument("--entry-link", help="External entry link (e.g., Isonen URL)")
    create_parser.add_argument(
        "--public",
        action="store_true",
        help="Make competition public immediately (default: hidden)",
    )
    create_parser.add_argument(
        "--no-points",
        dest="show_points",
        action="store_false",
        default=True,
        help="Disable individual points display",
    )
    create_parser.add_argument(
        "--tyrving-scoring",
        action="store_true",
        help="Use Tyrving combined events scoring tables instead of World Athletics",
    )
    create_parser.add_argument(
        "--no-numbering",
        dest="number_competitors",
        action="store_false",
        default=True,
        help="Skip automatic bib number assignment",
    )
    create_parser.add_argument(
        "--no-seeding",
        dest="random_seeding",
        action="store_false",
        default=True,
        help="Skip random seeding of start lists",
    )
    create_parser.set_defaults(func=cmd_create_competition)

    # Schedule events command
    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Schedule events (set start times) for a competition",
    )
    schedule_parser.add_argument(
        "competition_url",
        help="URL of the competition (e.g., https://norway.opentrack.run/x/2025/NOR/ser9-25/)",
    )
    schedule_parser.add_argument(
        "file",
        help="CSV file with schedule (columns: category,event,start_time)",
    )
    schedule_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    schedule_parser.set_defaults(func=cmd_schedule_events)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
