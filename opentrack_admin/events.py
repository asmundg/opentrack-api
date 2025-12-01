"""Event scheduling and management for OpenTrack competitions."""

import csv
import json
import logging
import re
from dataclasses import dataclass
from datetime import time
from io import StringIO
from pathlib import Path
from typing import Literal

from playwright.sync_api import Page

from .browser import OpenTrackSession, screenshot_on_error

# Set up logging
logger = logging.getLogger(__name__)

# Default checkpoint directory
CHECKPOINT_DIR = Path("checkpoints")

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
    "60m": "60 meter",
    "100m": "100 meter",
    "200m": "200 meter",
    "400m": "400 meter",
    
    # Middle/Long distance
    "800m": "800 meter",
    "1500m": "1500 meter",
    "3000m": "3000 meter",
    "5000m": "5000 meter",
    
    # Hurdles
    "60H": "60 meter hekk",
    "100H": "100 meter hekk",
    "110H": "110 meter hekk",
    "400H": "400 meter hekk",
    
    # Relays
    "4x100m": "4x100 meter",
    "4x400m": "4x400 meter",
}

# Throwing implement weights by category and event
# Format: {event_code: {gender: {age: weight_string}}}
# Gender: "G" for boys/men, "J" for girls/women
# Age groups: 10 (rekrutt/6-10), 11, 12, 13, 14, 15, 16, 17, 20 (U20), 23 (U23), 99 (Senior)
# Note: DT, JT, HT start at age 11 (not offered for rekrutt/10)
IMPLEMENT_WEIGHTS = {
    "SP": {  # Kule (Shot Put)
        "G": {10: "2", 11: "2", 12: "3", 13: "3", 14: "4", 15: "4", 16: "5", 17: "5", 20: "6", 23: "7,26", 99: "7,26"},
        "J": {10: "2", 11: "2", 12: "2", 13: "2", 14: "3", 15: "3", 16: "3", 17: "3", 20: "4", 23: "4", 99: "4"},
    },
    "DT": {  # Diskos (Discus) - starts at 11
        "G": {11: "0,6", 12: "0,75", 13: "0,75", 14: "1", 15: "1", 16: "1,5", 17: "1,5", 20: "1,75", 23: "2", 99: "2"},
        "J": {11: "0,6", 12: "0,6", 13: "0,6", 14: "0,75", 15: "0,75", 16: "1", 17: "1", 20: "1", 23: "1", 99: "1"},
    },
    "HT": {  # Slegge (Hammer) - starts at 11
        "G": {11: "2", 12: "2", 13: "3", 14: "4", 15: "4", 16: "5", 17: "5", 20: "7,26", 23: "7,26", 99: "7,26"},
        "J": {11: "2", 12: "2", 13: "2", 14: "3", 15: "3", 16: "3", 17: "3", 20: "4", 23: "4", 99: "4"},
    },
    "JT": {  # Spyd (Javelin) - starts at 11
        "G": {11: "400g", 12: "400g", 13: "400g", 14: "600g", 15: "600g", 16: "700g", 17: "700g", 20: "800g", 23: "800g", 99: "800g"},
        "J": {11: "400g", 12: "400g", 13: "400g", 14: "400g", 15: "400g", 16: "500g", 17: "500g", 20: "500g", 23: "600g", 99: "600g"},
    },
}

# Events that use implement weights
THROWING_EVENTS = {"SP", "DT", "HT", "JT"}


def get_implement_weight(event_code: str, category: str) -> str | None:
    """Get the implement weight for a throwing event and category.
    
    Args:
        event_code: Event code (SP, DT, HT, JT)
        category: Category like "G10", "J15", "M", "W"
        
    Returns:
        Weight string (e.g., "2", "0,75", "400g") or None if not a throwing event
    """
    if event_code not in THROWING_EVENTS:
        return None
    
    # Determine gender
    normalized = normalize_category(category)
    if normalized.startswith("G") or normalized in ("M", "U20", "U23"):
        gender = "G"
    elif normalized.startswith("J") or normalized in ("W", "K"):
        gender = "J"
    else:
        return None
    
    # Determine age
    age = get_category_age(category)
    if age is None:
        # Senior/U categories
        if normalized in ("M", "W", "K"):
            age = 99
        elif normalized in ("U20",):
            age = 20
        elif normalized in ("U23",):
            age = 23
        else:
            age = 99
    
    # Look up weight
    event_weights = IMPLEMENT_WEIGHTS.get(event_code, {})
    gender_weights = event_weights.get(gender, {})
    
    # Find the appropriate age bracket
    if age in gender_weights:
        return gender_weights[age]
    
    # Age not valid for this event (e.g., DT/JT/HT not offered for rekrutt/10)
    return None


class Checkpoint:
    """Track completed events to allow resuming after failures.
    
    Stores a simple JSON file with a set of completed event keys.
    """
    
    def __init__(self, name: str):
        """Create a checkpoint tracker.
        
        Args:
            name: Name for the checkpoint file (e.g., competition slug)
        """
        CHECKPOINT_DIR.mkdir(exist_ok=True)
        self.path = CHECKPOINT_DIR / f"{name}.json"
        self.completed: set[str] = set()
        self._load()
    
    def _load(self) -> None:
        """Load existing checkpoint data."""
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self.completed = set(data.get("completed", []))
                logger.info(f"Loaded checkpoint: {len(self.completed)} events already done")
            except (json.JSONDecodeError, KeyError):
                self.completed = set()
    
    def _save(self) -> None:
        """Save checkpoint data."""
        self.path.write_text(json.dumps({"completed": sorted(self.completed)}, indent=2))
    
    def is_done(self, key: str) -> bool:
        """Check if an event has been completed."""
        return key in self.completed
    
    def mark_done(self, key: str) -> None:
        """Mark an event as completed and save."""
        self.completed.add(key)
        self._save()
        logger.debug(f"Checkpoint: marked '{key}' as done")
    
    def clear(self) -> None:
        """Clear all checkpoint data."""
        self.completed = set()
        if self.path.exists():
            self.path.unlink()


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


def get_category_age(category: str) -> int | None:
    """Extract age from category like 'G10', 'J15', etc.
    
    Returns None for senior categories like 'M', 'W', 'U20', 'U23'.
    """
    normalized = normalize_category(category)
    # Match G/J followed by age number
    match = re.match(r"^[GJ](\d+)$", normalized)
    if match:
        return int(match.group(1))
    # Senior/U categories treated as 15+
    return None


def is_field_event(event_code: str) -> bool:
    """Check if event code is a field event (jumps/throws)."""
    return event_code in {"HJ", "LJ", "TJ", "PV", "SP", "DT", "JT", "HT"}


def is_horizontal_field_event(event_code: str) -> bool:
    """Check if event code is a horizontal field event (has attempts).
    
    Horizontal jumps and throws have a fixed number of attempts.
    Vertical jumps (HJ, PV) are height-based and don't use attempts.
    """
    return event_code in {"LJ", "TJ", "SP", "DT", "JT", "HT"}


@dataclass
class AttemptConfig:
    """Configuration for number of attempts in field events.
    
    Based on Norwegian athletics rules:
    - FIFA and rekrutt (6-10): 3 attempts, no cut
    - 11-12 years: 4 attempts, no cut
    - 13+ and seniors: 6 attempts with cut after 3 (top 8 continue)
    """
    attempts: int   # Total number of attempts
    field_cut: int  # Cut after this many attempts (0 = no cut)
    
    @classmethod
    def for_category(cls, category: str) -> "AttemptConfig":
        """Get attempt configuration for a category."""
        age = get_category_age(category)
        
        if age is not None and age <= 10:
            # FIFA and rekrutt: 3 attempts, no cut
            return cls(attempts=3, field_cut=0)
        elif age is not None and age <= 12:
            # 11-12 years: 4 attempts, no cut
            return cls(attempts=4, field_cut=0)
        else:
            # 13+ and seniors: 6 attempts, cut after 3
            return cls(attempts=6, field_cut=3)


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
    
    @property
    def is_field_event(self) -> bool:
        """Check if this is a field event (jumps/throws)."""
        return is_field_event(self.event)
    
    @property
    def is_horizontal_field_event(self) -> bool:
        """Check if this is a horizontal field event (has attempts).
        
        HJ and PV are vertical and height-based, no attempts.
        """
        return is_horizontal_field_event(self.event)
    
    @property
    def attempt_config(self) -> AttemptConfig:
        """Get the attempt configuration for this event's category."""
        return AttemptConfig.for_category(self.category)
    
    @property
    def is_throwing_event(self) -> bool:
        """Check if this is a throwing event (has implement weights)."""
        return self.event in THROWING_EVENTS
    
    @property
    def implement_weight(self) -> str | None:
        """Get the implement weight for this throwing event, or None."""
        return get_implement_weight(self.event, self.category)


class EventScheduler:
    """Handles scheduling events in an OpenTrack competition."""

    def __init__(self, session: OpenTrackSession):
        self.session = session
        self.page = session.page

    @screenshot_on_error
    def navigate_to_events_table(self) -> None:
        """Navigate to the Events Table tab from anywhere."""
        page = self.page
        
        # Navigate through Manage -> Events and scoring -> Events Table
        logger.info("Navigating to Events Table...")
        page.get_by_role("link", name=" Manage").click()
        page.get_by_role("link", name="Events and scoring").click()
        
        # Wait for the events form to load before clicking the tab
        page.locator("form").filter(has_text="IDNumCodeAge").wait_for(state="visible")
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

    @screenshot_on_error
    def set_event_attempts(self, config: AttemptConfig) -> None:
        """Set the number of attempts for the currently open field event.
        
        Assumes we're on an event detail page for a field event.
        """
        page = self.page
        
        logger.info(f"Setting attempts: {config.attempts}, field cut: {config.field_cut}")
        
        # Set total number of attempts
        attempts_field = page.get_by_role("spinbutton", name="Number of Attempts:")
        attempts_field.click()
        attempts_field.fill(str(config.attempts))
        
        # Set field cut (0 = no cut, 3 = cut after 3 attempts)
        cut_field = page.get_by_role("spinbutton", name="Field Cut:")
        cut_field.click()
        cut_field.fill(str(config.field_cut))
        
        # Save and wait for confirmation banner
        page.get_by_role("button", name="Save").click()
        page.get_by_text("Event data saved").wait_for(state="visible", timeout=10000)
        logger.info("Attempts saved")

    @screenshot_on_error
    def set_implement_weight(self, weight: str, num_competitors: int = 20) -> None:
        """Set the implement weight for all competitors in a throwing event.
        
        Navigates to the attempts/heights editor and fills in the weight for all rows.
        Uses Handsontable grid - finds Weight column by header, then fills each row.
        
        Args:
            weight: The weight string (e.g., "2", "0,75", "400g")
            num_competitors: Max number of competitor rows to fill (default 20)
        """
        page = self.page
        
        logger.info(f"Setting implement weight: {weight}")
        
        # Click View to see competitors, then Edit to edit weights
        page.get_by_role("link", name="View").click()
        page.wait_for_load_state("networkidle")
        # Edit button has complex structure, use the URL pattern
        page.locator("a[href*='/edit/']").filter(has_text="Edit").click()
        page.wait_for_load_state("networkidle")
        
        # Find the Weight column header and click it to select the column
        table = page.locator("#attempts_ht .ht_master table.htCore")
        
        # Find Weight header - click on first row's Weight cell to start
        weight_header = table.locator("thead th").filter(has_text="Weight")
        if weight_header.count() == 0:
            raise RuntimeError("Could not find 'Weight' column in table")
        
        # Get the bounding box of the Weight header to find the column position
        weight_header_box = weight_header.bounding_box()
        if not weight_header_box:
            raise RuntimeError("Could not get Weight column position")
        
        # X position is the center of the Weight column
        weight_x = weight_header_box["x"] + weight_header_box["width"] / 2
        
        # Get all data rows
        rows = table.locator("tbody tr")
        row_count = rows.count()
        logger.info(f"Found {row_count} rows in table")
        
        for i in range(min(row_count, num_competitors)):
            row = rows.nth(i)
            # Check if this row has data (first cell has content)
            first_cell = row.locator("td").first
            if not first_cell.text_content():
                logger.info(f"Row {i+1} is empty, stopping")
                break
            
            # Get the row's Y position
            row_box = row.bounding_box()
            if not row_box:
                continue
            
            row_y = row_box["y"] + row_box["height"] / 2
            
            # Click at the Weight column position for this row
            page.mouse.click(weight_x, row_y)
            page.wait_for_timeout(100)
            
            # Type the weight (will replace cell content when cell is active)
            page.keyboard.type(weight)
            page.keyboard.press("Enter")
            
            logger.debug(f"Set weight for row {i+1}")
        
        # Save
        page.get_by_role("button", name="Save").first.click()
        page.wait_for_load_state("networkidle")
        logger.info("Implement weights saved")

    def schedule_event(self, schedule: EventSchedule) -> bool:
        """Find an event, set its start time, and configure attempts/weights for field events.
        
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
        
        # Configure attempts for horizontal field events (not HJ/PV)
        if schedule.is_horizontal_field_event:
            self.set_event_attempts(schedule.attempt_config)
        
        # Set implement weights for throwing events
        if schedule.is_throwing_event and schedule.implement_weight:
            self.set_implement_weight(schedule.implement_weight)
        
        self.navigate_to_events_table()
        return True

    def schedule_events(
        self, schedules: list[EventSchedule], checkpoint_name: str | None = None
    ) -> dict[str, bool]:
        """Schedule multiple events.
        
        Args:
            schedules: List of events to schedule
            checkpoint_name: Optional name for checkpoint file to allow resuming.
                           If provided, completed events are skipped on restart.
            
        Returns:
            Dict mapping search terms to success status
        """
        results = {}
        checkpoint = Checkpoint(checkpoint_name) if checkpoint_name else None
        
        # Count how many we'll skip
        if checkpoint:
            skip_count = sum(1 for s in schedules if checkpoint.is_done(s.search_term))
            if skip_count > 0:
                logger.info(f"Skipping {skip_count} already-completed events")
        
        logger.info(f"Starting to schedule {len(schedules)} events")
        self.navigate_to_events_table()
        
        for i, schedule in enumerate(schedules, 1):
            # Skip FIFA category (not defined in OpenTrack)
            if schedule.category.upper() == "FIFA":
                logger.info(f"Skipping {i}/{len(schedules)}: {schedule.search_term} (FIFA category)")
                continue
            
            # Skip if already done
            if checkpoint and checkpoint.is_done(schedule.search_term):
                logger.info(f"Skipping {i}/{len(schedules)}: {schedule.search_term} (already done)")
                results[schedule.search_term] = True
                continue
            
            logger.info(f"Processing event {i}/{len(schedules)}")
            self.schedule_event(schedule)
            results[schedule.search_term] = True
            
            # Mark as done in checkpoint
            if checkpoint:
                checkpoint.mark_done(schedule.search_term)
        
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
