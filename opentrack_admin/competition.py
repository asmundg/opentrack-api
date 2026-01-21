"""Competition creation and management for OpenTrack."""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Literal

from .browser import OpenTrackSession

logger = logging.getLogger(__name__)


# Competition type mapping to OpenTrack values
COMPETITION_TYPES = {
    "track": "TRACK",
    "indoor": "INDOOR",
    "road": "ROAD",
    "cross_country": "XC",
    "trail": "TRAIL",
}

# Combined events scoring tables
COMBINED_EVENTS_TABLES = {
    "world_athletics": "WA",
    "tyrving": "TYRV",
}


@dataclass
class CompetitionDetails:
    """Details for creating a new competition."""

    # Required fields
    name: str  # Full name, e.g., "Seriestevne 9-2025"
    slug: str  # URL slug, e.g., "ser9-25"
    start_date: date
    contact_email: str
    organiser_search: str  # Search term to find organiser, e.g., "BULTF"
    
    # Optional with defaults
    short_name: str = ""  # If empty, OpenTrack may auto-generate
    end_date: date | None = None  # None = same as start_date
    competition_type: Literal["track", "indoor", "road", "cross_country", "trail"] = "track"
    
    # Display settings
    website: str = ""
    external_entry_link: str = ""  # e.g., Isonen link

    # Scoring settings
    combined_events_table: Literal["world_athletics", "tyrving"] | None = None  # None = use default

    def __post_init__(self):
        if self.end_date is None:
            self.end_date = self.start_date


class CompetitionCreator:
    """Handles creating new competitions on OpenTrack."""

    def __init__(self, session: OpenTrackSession):
        self.session = session
        self.page = session.page

    def create_competition(self, details: CompetitionDetails) -> str:
        """Create a new competition and return its URL.

        Args:
            details: Competition configuration

        Returns:
            URL of the created competition
        """
        logger.info("Starting competition creation: %s", details.name)

        # Ensure we're logged in
        if not self.session.is_logged_in():
            logger.info("Not logged in, logging in...")
            self.session.login()

        # Step 1: Navigate and create basic competition (includes initial entry setup)
        logger.info("Step 1/7: Creating basic competition...")
        self._create_basic_competition(details)

        # Step 2: Configure advanced settings (hide from public)
        logger.info("Step 2/7: Configuring advanced settings...")
        self._configure_advanced_settings()

        # Step 3: Configure display settings (website, entry link, points, hide results/competitors)
        logger.info("Step 3/7: Configuring display settings...")
        self._configure_display_settings(details)

        # Step 4: Configure scoring (e.g., Tyrving tables)
        if details.combined_events_table:
            logger.info("Step 4/7: Configuring scoring...")
            self._configure_scoring(details)
        else:
            logger.info("Step 4/7: Skipping scoring (not configured)")

        # Step 5: Configure photofinish (FinishLynx)
        logger.info("Step 5/7: Configuring photofinish...")
        self._configure_photofinish()

        # Step 6: Number competitors
        logger.info("Step 6/7: Numbering competitors...")
        self._number_competitors()

        # Step 7: Apply random seeding
        logger.info("Step 7/7: Applying random seeding...")
        self._apply_random_seeding()

        logger.info("Competition created successfully: %s", self.page.url)
        return self.page.url

    def _create_basic_competition(self, details: CompetitionDetails) -> None:
        """Navigate to competition creation and fill basic info."""
        page = self.page

        # Navigate to competition creation
        logger.debug("Navigating to competition creation form")
        page.get_by_role("link", name="Competitions").click()
        page.get_by_role("button", name="New Competition ").click()

        # Fill basic info
        logger.debug("Filling basic competition info")
        page.get_by_role("textbox", name="* Full name:").click()
        page.get_by_role("textbox", name="* Full name:").fill(details.name)

        if details.short_name:
            page.get_by_role("textbox", name="Short name:").fill(details.short_name)

        # Dates
        logger.debug("Setting dates: %s to %s", details.start_date, details.end_date)
        page.get_by_role("textbox", name="* Date:").fill(details.start_date.isoformat())
        if details.end_date and details.end_date != details.start_date:
            page.get_by_role("textbox", name="Finish Date:").fill(details.end_date.isoformat())
        else:
            page.get_by_role("textbox", name="Finish Date:").fill(details.start_date.isoformat())

        # Slug
        logger.debug("Setting slug: %s", details.slug)
        page.get_by_role("textbox", name="* Slug:").click()
        page.get_by_role("textbox", name="* Slug:").fill(details.slug)

        # Competition type
        comp_type_value = COMPETITION_TYPES.get(details.competition_type, "TRACK")
        logger.debug("Setting competition type: %s", comp_type_value)
        page.get_by_label("Type:").select_option(comp_type_value)

        # Contact email
        logger.debug("Setting contact email: %s", details.contact_email)
        page.get_by_role("textbox", name="* Contact email:").click()
        page.get_by_role("textbox", name="* Contact email:").fill(details.contact_email)

        # Organiser (uses Select2 search widget)
        logger.debug("Selecting organiser: %s", details.organiser_search)
        page.locator("#select2-id_organiser-container").click()
        searchbox = page.get_by_role("searchbox")
        searchbox.fill(details.organiser_search)
        # Wait for the highlighted option to appear and click it
        highlighted_option = page.locator("li.select2-results__option--highlighted")
        highlighted_option.wait_for(state="visible")
        highlighted_option.click()

        # Create the competition
        logger.debug("Submitting competition creation form")
        page.get_by_role("button", name="Create").nth(1).click()
        page.wait_for_load_state("networkidle")

        # Immediately enable entries after creation
        logger.debug("Enabling entries")
        page.get_by_role("link", name="Manage entries").click()
        page.get_by_text("I confirm that I have read").click()
        page.get_by_role("button", name="Go").click()
        page.wait_for_load_state("networkidle")
        logger.debug("Basic competition created and entries enabled")

    def _configure_advanced_settings(self) -> None:
        """Configure advanced settings - hide competition from public."""
        page = self.page

        logger.debug("Setting competition to hidden from public")
        hide_checkbox = page.get_by_role("checkbox", name="Hide from public:")
        if not hide_checkbox.is_checked():
            hide_checkbox.check()

        logger.debug("Saving advanced settings")
        page.locator("button[name=\"adv_submit\"]").click()
        page.wait_for_load_state("networkidle")

    def _configure_display_settings(self, details: CompetitionDetails) -> None:
        """Configure display settings like website and entry links."""
        page = self.page

        # Navigate to Display tab
        logger.debug("Navigating to Display tab")
        page.get_by_role("link", name="Display ").click()

        # Website
        if details.website:
            logger.debug("Setting website: %s", details.website)
            page.get_by_role("textbox", name="Website:").click()
            page.get_by_role("textbox", name="Website:").fill(details.website)

        # External entry link (e.g., Isonen)
        if details.external_entry_link:
            logger.debug("Setting external entry link: %s", details.external_entry_link)
            page.get_by_role("textbox", name="External entry link:").fill(details.external_entry_link)

        # Hide results and competitors (useful during setup)
        logger.debug("Hiding results and competitors")
        hide_results = page.get_by_role("checkbox", name="Hide results:")
        if not hide_results.is_checked():
            hide_results.check()
        hide_competitors = page.get_by_role("checkbox", name="Hide competitors:")
        if not hide_competitors.is_checked():
            hide_competitors.check()

        # Save display settings
        logger.debug("Saving display settings")
        page.get_by_role("button", name="Save").nth(1).click()
        page.wait_for_load_state("networkidle")

        # Individual points setting (separate save button)
        logger.debug("Enabling individual points display")
        points_checkbox = page.get_by_role("checkbox", name="Show individual points?")
        if not points_checkbox.is_checked():
            points_checkbox.check()
        page.get_by_role("button", name="Save").nth(3).click()
        page.wait_for_load_state("networkidle")

    def _configure_scoring(self, details: CompetitionDetails) -> None:
        """Configure scoring settings like combined events tables."""
        page = self.page

        # Navigate to Events and scoring via World Athletics link
        logger.debug("Navigating to Events and scoring")
        page.locator("a").filter(has_text="World Athletics").click()
        page.get_by_role("link", name="Events and scoring").click()

        # Go to Scoring -> Combined Events tab
        logger.debug("Navigating to Combined Events tab")
        page.get_by_role("tab", name="Scoring").click()
        page.get_by_role("tab", name="Combined Events").click()

        # Select the combined events table
        if details.combined_events_table:
            table_value = COMBINED_EVENTS_TABLES.get(details.combined_events_table, "WA")
            logger.debug("Setting combined events table: %s", table_value)
            page.get_by_label("Combined Events tables:").select_option(table_value)

        logger.debug("Saving scoring settings")
        page.get_by_role("button", name="Save").click()
        page.wait_for_load_state("networkidle")

    def _configure_photofinish(self) -> None:
        """Configure FinishLynx photofinish integration."""
        page = self.page

        # Navigate to TV and photofinish -> FinishLynx
        logger.debug("Navigating to FinishLynx settings")
        page.get_by_role("link", name="TV and photofinish").click()
        page.get_by_role("link", name="FinishLynx").click()

        # Enable photofinish file generation
        logger.debug("Enabling photofinish settings")
        photofinish_files = page.get_by_role("checkbox", name="Photofinish files should")
        if not photofinish_files.is_checked():
            photofinish_files.check()

        # Enable results from photofinish
        results_from_photofinish = page.get_by_role("checkbox", name="Results from photofinish")
        if not results_from_photofinish.is_checked():
            results_from_photofinish.check()

        logger.debug("Saving photofinish settings")
        page.get_by_role("button", name="Save").click()
        page.wait_for_load_state("networkidle")

    def _number_competitors(self) -> None:
        """Automatically assign bib numbers to all competitors."""
        page = self.page

        # Navigate to competitor numbering
        logger.debug("Navigating to competitor numbering")
        page.get_by_role("button", name="Manage competitors ").click()
        page.get_by_role("link", name="Numbering").click()

        # Apply numbering - button text includes count, so use regex/partial match
        logger.debug("Applying bib numbers")
        page.get_by_role("button", name="Save and apply to").click()
        page.wait_for_load_state("networkidle")
        logger.debug("Bib numbers assigned")

    def _apply_random_seeding(self) -> None:
        """Apply random seeding to all start lists."""
        page = self.page

        # Navigate to seeding
        logger.debug("Navigating to seeding")
        page.get_by_role("button", name="Manage competitors ").click()
        page.get_by_role("link", name="Seeding").click()

        # Fetch all start lists first
        logger.debug("Fetching all start lists")
        page.get_by_text("Fetch all start lists Fetch").click()
        page.wait_for_load_state("networkidle")

        # Apply random order
        logger.debug("Applying random order")
        page.get_by_role("button", name="Random order").click()
        page.wait_for_load_state("networkidle")
        logger.debug("Random seeding applied")
