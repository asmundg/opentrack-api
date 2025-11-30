"""Event scheduling and management for OpenTrack competitions."""

import csv
import logging
import re
from dataclasses import dataclass
from datetime import time
from io import StringIO
from typing import Literal

from playwright.sync_api import Page

from .browser import OpenTrackSession, screenshot_on_error

# Set up logging
logger = logging.getLogger(__name__)

# Event code to Norwegian name mapping
EVENT_NAMES = {
    # Jumps
    "HJ": "Høyde",
    "LJ": "Lengde",
    "TJ": "Tresteg",
    "PV": "Stav",
    
    # Throws
    "SP": "Kule",
    "DT": "Diskos",
    "JT": "Spyd",
    "HT": "Slegge",
    
    # Sprints
    "60m": "60m",
    "100m": "100m",
    "200m": "200m",
    "400m": "400m",
    
    # Middle/Long distance
    "800m": "800m",
    "1500m": "1500m",
    "3000m": "3000m",
    "5000m": "5000m",
    
    # Hurdles
    "60H": "60m hekk",
    "100H": "100m hekk",
    "110H": "110m hekk",
    "400H": "400m hekk",
    
    # Relays
    "4x100m": "4x100m",
    "4x400m": "4x400m",
}


def get_event_name(code: str) -> str:
    """Get the Norwegian event name for an event code.
    
    Raises:
        KeyError: If the event code is not in the mapping.
    """
    if code not in EVENT_NAMES:
        raise KeyError(f"Unknown event code: '{code}'. Add it to EVENT_NAMES in events.py")
    return EVENT_NAMES[code]


def normalize_category(category: str) -> str:
    """Normalize category name for OpenTrack search.
    
    Converts 'G-rekrutt' -> 'G10', 'J-rekrutt' -> 'J10', etc.
    """
    if category.endswith("-rekrutt"):
        # G-rekrutt -> G10, J-rekrutt -> J10
        prefix = category.replace("-rekrutt", "")
        return f"{prefix}10"
    return category


@dataclass
class EventSchedule:
    """A scheduled event with category, event code, and start time.
    
    Examples:
        EventSchedule("G10", "60m", time(10, 0))     # G10 60m at 10:00
        EventSchedule("J15", "HJ", time(10, 30))     # J15 Høyde at 10:30
        EventSchedule("M", "SP", time(11, 0))        # Men Kule at 11:00
    """
    category: str  # e.g., "G10", "J15", "M", "W", "G-rekrutt"
    event: str     # e.g., "60m", "HJ", "SP", "LJ"
    start_time: time
    
    @property
    def event_name(self) -> str:
        """Get the Norwegian name for the event."""
        return get_event_name(self.event)
    
    @property
    def search_category(self) -> str:
        """Get the normalized category for searching."""
        return normalize_category(self.category)
    
    @property
    def search_term(self) -> str:
        """Generate search term for finding this event."""
        return f"{self.search_category} {self.event_name}"


class EventScheduler:
    """Handles scheduling events in an OpenTrack competition."""

    def __init__(self, session: OpenTrackSession):
        self.session = session
        self.page = session.page

    def navigate_to_events_table(self) -> None:
        """Navigate to the Events Table tab."""
        page = self.page
        
        # Navigate through Manage -> Events and scoring -> Events Table
        logger.info("Navigating to Events Table...")
        page.get_by_role("link", name=" Manage").click()
        page.get_by_role("link", name="Events and scoring").click()
        page.get_by_role("tab", name=" Events Table").click()
        page.wait_for_load_state("networkidle")
        
        logger.info("Events table ready")

    @screenshot_on_error
    def find_and_click_event(self, schedule: EventSchedule) -> bool:
        """Find an event by category and code, then click to open it.
        
        Args:
            schedule: The event to find
            
        Returns:
            True if event was found and clicked, False otherwise
        """
        page = self.page
        
        logger.info(f"Searching for event: {schedule.search_term}")
        
        # Use the search box to filter
        search_box = page.get_by_role("textbox", name="Search")
        search_box.click()
        search_box.fill(schedule.search_term)
        
        # Click the search button
        page.locator("#search_advanced_btn").click()
        
        # Wait for table to filter
        page.wait_for_load_state("networkidle")
        
        # Find event links (T01, T02, etc. for track, F01, F02, etc. for field) in the filtered results
        # These are links starting with "T" or "F" followed by digits
        event_link = page.locator("a").filter(has_text=re.compile(r"^[TF]\d+$"))
        
        count = event_link.count()
        logger.info(f"Found {count} event link(s)")
        
        if count > 0:
            first_link = event_link.first
            logger.info(f"Clicking event link: {first_link.text_content()}")
            first_link.click()
            page.wait_for_load_state("networkidle")
            return True
        
        # No event found - raise error (screenshot taken by wrapper)
        raise RuntimeError(f"No event found for: {schedule.search_term}")

    @screenshot_on_error
    def set_event_start_time(self, start_time: time) -> None:
        """Set the start time for the currently open event.
        
        Assumes we're on an event detail page.
        """
        page = self.page
        
        # Format time as HH:MM
        time_str = start_time.strftime("%H:%M")
        logger.info(f"Setting start time to: {time_str}")
        
        # Find and fill the start time field
        time_field = page.get_by_role("textbox", name="Round 1 Time:")
        
        if time_field.count() == 0:
            raise RuntimeError("'Round 1 Time:' field not found")
        
        time_field.click()
        time_field.fill(time_str)
        
        # Save and wait for confirmation banner
        page.get_by_role("button", name="Save").click()
        page.get_by_text("Event data saved").wait_for(state="visible", timeout=10000)
        logger.info("Event saved")

    def schedule_event(self, schedule: EventSchedule) -> bool:
        """Find an event and set its start time.
        
        Args:
            schedule: Event with category, code, and start time
            
        Returns:
            True if successful
            
        Raises:
            RuntimeError: If event not found or other error
        """
        logger.info(f"=== Scheduling: {schedule.search_term} @ {schedule.start_time} ===")
        self.find_and_click_event(schedule)
        self.set_event_start_time(schedule.start_time)
        self._navigate_back_to_events_table()
        return True

    def _navigate_back_to_events_table(self) -> None:
        """Navigate back to the Events Table tab."""
        logger.info("Navigating back to Events Table...")
        self.page.get_by_role("tab", name="Events Table").click()
        self.page.wait_for_load_state("networkidle")

    def schedule_events(self, schedules: list[EventSchedule]) -> dict[str, bool]:
        """Schedule multiple events.
        
        Args:
            schedules: List of events to schedule
            
        Returns:
            Dict mapping search terms to success status
        """
        results = {}
        
        logger.info(f"Starting to schedule {len(schedules)} events")
        self.navigate_to_events_table()
        
        for i, schedule in enumerate(schedules, 1):
            logger.info(f"Processing event {i}/{len(schedules)}")
            self.schedule_event(schedule)
            results[schedule.search_term] = True
        
        logger.info(f"Finished scheduling. Success: {sum(results.values())}/{len(results)}")
        return results


def parse_time(time_str: str) -> time:
    """Parse a time string like '17:00' or '17:25'."""
    hour, minute = map(int, time_str.strip().split(":"))
    return time(hour, minute)


def parse_schedule_csv(content: str) -> list[EventSchedule]:
    """Parse a CSV schedule file.
    
    Expected format (with header):
        category,event,start_time
        J14,LJ,17:00
        G-rekrutt,HJ,17:00
        G11,60m,17:25
    
    Args:
        content: CSV file content as string
        
    Returns:
        List of EventSchedule objects
    """
    schedules = []
    
    reader = csv.DictReader(StringIO(content))
    
    for row in reader:
        try:
            category = row["category"].strip()
            event = row["event"].strip()
            start_time = parse_time(row["start_time"])
            
            schedules.append(EventSchedule(
                category=category,
                event=event,
                start_time=start_time,
            ))
        except (KeyError, ValueError) as e:
            # Skip invalid rows but could log warning
            continue
    
    return schedules
