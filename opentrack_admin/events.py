"""Event scheduling and management for OpenTrack competitions."""

import csv
import logging
from dataclasses import dataclass
from datetime import time
from io import StringIO
from typing import Literal

from playwright.sync_api import Page

from .browser import OpenTrackSession

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class EventSchedule:
    """A scheduled event with category, event code, and start time.
    
    Examples:
        EventSchedule("G10", "60m", time(10, 0))     # G10 60m at 10:00
        EventSchedule("J15", "HJ", time(10, 30))     # J15 High Jump at 10:30
        EventSchedule("M", "SP", time(11, 0))        # Men Shot Put at 11:00
    """
    category: str  # e.g., "G10", "J15", "M", "W", "G-rekrutt"
    event: str     # e.g., "60m", "HJ", "SP", "LJ"
    start_time: time
    
    @property
    def search_term(self) -> str:
        """Generate search term for finding this event."""
        return f"{self.category} {self.event}"


class EventScheduler:
    """Handles scheduling events in an OpenTrack competition."""

    def __init__(self, session: OpenTrackSession):
        self.session = session
        self.page = session.page

    def navigate_to_events_table(self) -> None:
        """Navigate to the Events Table tab."""
        page = self.page
        
        # Navigate through Manage -> Events and scoring -> Events Table
        logger.info("Clicking 'Manage' link...")
        page.get_by_role("link", name=" Manage").click()
        
        logger.info("Clicking 'Events and scoring' link...")
        page.get_by_role("link", name="Events and scoring").click()
        
        logger.info("Clicking 'Events Table' tab...")
        page.get_by_role("tab", name=" Events Table").click()
        page.wait_for_load_state("networkidle")
        
        logger.info("Events table ready")

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
        
        # Wait for table to filter
        logger.debug("Waiting for search results...")
        page.wait_for_timeout(500)  # Brief wait for filtering
        
        # Find the first event link (T01, T02, etc.) in the filtered results
        # These are in the first column and link to the event detail page
        event_link = page.get_by_role("link").filter(has_text=lambda t: t and t.startswith("T"))
        
        count = event_link.count()
        logger.info(f"Found {count} event link(s) matching pattern")
        
        if count > 0:
            first_link = event_link.first
            link_text = first_link.text_content()
            logger.info(f"Clicking event link: {link_text}")
            first_link.click()
            page.wait_for_load_state("networkidle")
            return True
        
        logger.warning(f"No event found for: {schedule.search_term}")
        return False

    def set_event_start_time(self, start_time: time) -> None:
        """Set the start time for the currently open event.
        
        Assumes we're on an event detail page.
        """
        page = self.page
        
        # Format time as HH:MM
        time_str = start_time.strftime("%H:%M")
        logger.info(f"Setting start time to: {time_str}")
        
        # Find and fill the start time field
        # This selector may need adjustment based on actual page structure
        logger.debug("Looking for start time field...")
        time_field = page.get_by_role("textbox", name="Start time")
        if time_field.count() == 0:
            logger.debug("Trying alternate selector: input[name='start_time']")
            time_field = page.locator("input[name='start_time']")
        
        if time_field.count() == 0:
            logger.error("Could not find start time field!")
            logger.debug(f"Current URL: {page.url}")
            raise RuntimeError("Start time field not found")
        
        time_field.click()
        time_field.fill(time_str)
        
        # Save
        logger.info("Clicking Save...")
        page.get_by_role("button", name="Save").click()
        page.wait_for_load_state("networkidle")
        logger.info("Event saved")

    def schedule_event(self, schedule: EventSchedule) -> bool:
        """Find an event and set its start time.
        
        Args:
            schedule: Event with category, code, and start time
            
        Returns:
            True if successful, False if event not found
        """
        logger.info(f"=== Scheduling: {schedule.search_term} @ {schedule.start_time} ===")
        try:
            if self.find_and_click_event(schedule):
                self.set_event_start_time(schedule.start_time)
                return True
        except Exception as e:
            logger.error(f"Error scheduling {schedule.search_term}: {e}")
            # Take a screenshot for debugging
            try:
                self.page.screenshot(path=f"error_{schedule.category}_{schedule.event}.png")
                logger.info(f"Screenshot saved: error_{schedule.category}_{schedule.event}.png")
            except:
                pass
        return False

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
            success = self.schedule_event(schedule)
            results[schedule.search_term] = success
            
            # Navigate back to events table for next event
            if success:
                logger.info("Navigating back to Events Table...")
                page = self.page
                page.get_by_role("tab", name=" Events Table").click()
                page.wait_for_load_state("networkidle")
        
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
