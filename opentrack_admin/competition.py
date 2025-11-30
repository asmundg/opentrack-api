"""Competition creation and management for OpenTrack."""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from playwright.sync_api import Page, expect

from .browser import OpenTrackSession


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
    hide_from_public: bool = True  # Start hidden while setting up
    show_individual_points: bool = True
    
    # Scoring settings
    combined_events_table: Literal["world_athletics", "tyrving"] | None = None  # None = use default
    
    # Competitor settings
    auto_number_competitors: bool = True  # Automatically assign bib numbers
    random_seeding: bool = True  # Apply random seeding to start lists

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
        # Ensure we're logged in
        if not self.session.is_logged_in():
            self.session.login()

        # Step 1: Navigate and create basic competition
        self._create_basic_competition(details)
        
        # Step 2: Configure advanced settings (hide from public)
        self._configure_advanced_settings(details)
        
        # Step 3: Configure display settings (website, entry link, points)
        self._configure_display_settings(details)
        
        # Step 4: Configure scoring (e.g., Tyrving tables)
        if details.combined_events_table:
            self._configure_scoring(details)
        
        # Step 5: Enable entries
        self._enable_entries()
        
        # Step 6: Number competitors (if requested)
        if details.auto_number_competitors:
            self._number_competitors()
        
        # Step 7: Apply random seeding (if requested)
        if details.random_seeding:
            self._apply_random_seeding()
        
        return self.page.url

    def _create_basic_competition(self, details: CompetitionDetails) -> None:
        """Navigate to competition creation and fill basic info."""
        page = self.page
        
        # Navigate to competition creation
        page.get_by_role("link", name="Competitions").click()
        page.get_by_role("button", name="New Competition ").click()
        
        # Fill basic info
        page.get_by_role("textbox", name="* Full name:").click()
        page.get_by_role("textbox", name="* Full name:").fill(details.name)
        
        if details.short_name:
            page.get_by_role("textbox", name="Short name:").fill(details.short_name)
        
        # Dates
        page.get_by_role("textbox", name="* Date:").fill(details.start_date.isoformat())
        if details.end_date and details.end_date != details.start_date:
            page.get_by_role("textbox", name="Finish Date:").fill(details.end_date.isoformat())
        else:
            page.get_by_role("textbox", name="Finish Date:").fill(details.start_date.isoformat())
        
        # Slug
        page.get_by_role("textbox", name="* Slug:").click()
        page.get_by_role("textbox", name="* Slug:").fill(details.slug)
        
        # Competition type
        comp_type_value = COMPETITION_TYPES.get(details.competition_type, "TRACK")
        page.get_by_label("Type:").select_option(comp_type_value)
        
        # Contact email
        page.get_by_role("textbox", name="* Contact email:").click()
        page.get_by_role("textbox", name="* Contact email:").fill(details.contact_email)
        
        # Organiser (uses Select2 search widget)
        page.locator("#select2-id_organiser-container").click()
        page.get_by_role("searchbox").fill(details.organiser_search)
        # Wait for and click the first matching option
        page.get_by_role("option").first.click()
        
        # Create the competition
        page.get_by_role("button", name="Create").nth(1).click()
        page.wait_for_load_state("networkidle")

    def _configure_advanced_settings(self, details: CompetitionDetails) -> None:
        """Configure advanced settings like visibility."""
        page = self.page
        
        if details.hide_from_public:
            hide_checkbox = page.get_by_role("checkbox", name="Hide from public:")
            if not hide_checkbox.is_checked():
                hide_checkbox.check()
        
        page.locator("button[name=\"adv_submit\"]").click()
        page.wait_for_load_state("networkidle")

    def _configure_display_settings(self, details: CompetitionDetails) -> None:
        """Configure display settings like website and entry links."""
        page = self.page
        
        # Navigate to Display tab
        page.get_by_role("link", name="Display ").click()
        
        # Website
        if details.website:
            page.get_by_role("textbox", name="Website:").click()
            page.get_by_role("textbox", name="Website:").fill(details.website)
        
        # External entry link (e.g., Isonen)
        if details.external_entry_link:
            page.get_by_role("textbox", name="External entry link:").fill(details.external_entry_link)
        
        # Save display settings
        page.get_by_role("button", name="Save").nth(1).click()
        page.wait_for_load_state("networkidle")
        
        # Individual points setting (separate save button)
        if details.show_individual_points:
            points_checkbox = page.get_by_role("checkbox", name="Show individual points?")
            if not points_checkbox.is_checked():
                points_checkbox.check()
            page.get_by_role("button", name="Save").nth(3).click()
            page.wait_for_load_state("networkidle")

    def _configure_scoring(self, details: CompetitionDetails) -> None:
        """Configure scoring settings like combined events tables."""
        page = self.page
        
        # Navigate to Events and scoring via World Athletics link
        page.locator("a").filter(has_text="World Athletics").click()
        page.get_by_role("link", name="Events and scoring").click()
        
        # Go to Scoring -> Combined Events tab
        page.get_by_role("tab", name="Scoring").click()
        page.get_by_role("tab", name="Combined Events").click()
        
        # Select the combined events table
        if details.combined_events_table:
            table_value = COMBINED_EVENTS_TABLES.get(details.combined_events_table, "WA")
            page.get_by_label("Combined Events tables:").select_option(table_value)
        
        page.get_by_role("button", name="Save").click()
        page.wait_for_load_state("networkidle")

    def _enable_entries(self) -> None:
        """Enable the entries system for the competition."""
        page = self.page
        
        # Navigate back to competition home
        page.get_by_role("link", name="Home", exact=True).click()
        
        # Go to manage entries
        page.get_by_role("link", name="Competition details").click()
        page.get_by_role("link", name="Manage entries").click()
        
        # Enable entries (first Go button)
        page.get_by_role("button", name="Go").click()
        
        # Accept terms
        page.get_by_text("I confirm that I have read").click()
        page.get_by_role("button", name="Go").click()
        page.wait_for_load_state("networkidle")

    def _number_competitors(self) -> None:
        """Automatically assign bib numbers to all competitors."""
        page = self.page
        
        # Navigate to competitor numbering
        page.get_by_role("button", name="Manage competitors ").click()
        page.get_by_role("link", name="Numbering").click()
        
        # Apply numbering - button text includes count, so use regex/partial match
        page.get_by_role("button", name="Save and apply to").click()
        page.wait_for_load_state("networkidle")

    def _apply_random_seeding(self) -> None:
        """Apply random seeding to all start lists."""
        page = self.page
        
        # Navigate to seeding
        page.get_by_role("button", name="Manage competitors ").click()
        page.get_by_role("link", name="Seeding").click()
        
        # Fetch all start lists first
        page.get_by_text("Fetch all start lists Fetch").click()
        page.wait_for_load_state("networkidle")
        
        # Apply random order
        page.get_by_role("button", name="Random order").click()
        page.wait_for_load_state("networkidle")
