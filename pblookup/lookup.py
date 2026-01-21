"""Main PB lookup functionality."""
import sys
from typing import Optional

from .models import Result, Athlete
from .scraper import MinfriidrettsScraper
from .matching import extract_surname, find_best_match
from .events import standardize_event_name


class PBLookupService:
    """Service for looking up Personal Bests of Norwegian track and field athletes."""
    
    def __init__(self, debug: bool = False):
        self.scraper = MinfriidrettsScraper(debug=debug)
        self.debug = debug
        
    def lookup_pb(
        self,
        name: str,
        club: str,
        birth_date: str,
        event: str,
        category: str = "",
        competition_year: Optional[int] = None
    ) -> Optional[Result]:
        """
        Look up personal best for an athlete in a specific event.
        
        Args:
            name: Athlete's full name
            club: Current or historical club affiliation
            birth_date: Date of birth in DD.MM.YYYY format (for disambiguation)
            event: Track and field event (e.g., "100m", "Long Jump", "Shot Put")
            category: Age category like 'J15', 'G12' for validation (optional)
            competition_year: Year of competition for age validation (defaults to current year)
        
        Returns:
            Result object with PB details or None if no result found
        """
        # Standardize event name
        standardized_event = standardize_event_name(event)

        # Extract surname for search
        surname = extract_surname(name)
        if not surname:
            if self.debug:
                print(f"Could not extract surname from '{name}'", file=sys.stderr)
            return None

        if self.debug:
            print(f"Searching for athletes with surname '{surname}'", file=sys.stderr)

        # Search for athletes with matching surname
        try:
            candidate_athletes = self.scraper.search_athletes_by_surname(surname)
            if self.debug:
                print(f"Found {len(candidate_athletes)} candidates", file=sys.stderr)
        except Exception as e:
            if self.debug:
                print(f"Error during search: {e}", file=sys.stderr)
            return None
        
        if not candidate_athletes:
            if self.debug:
                print(f"No athletes found with surname '{surname}'", file=sys.stderr)
            return None
        
        # Filter candidates by name similarity, club, birth_date
        if self.debug:
            print(f"DEBUG: Filtering {len(candidate_athletes)} candidates:", file=sys.stderr)
            for i, candidate in enumerate(candidate_athletes):
                print(f"  {i+1}. ID: {candidate.id}, Name: '{candidate.name}', Club: '{candidate.club or 'None'}', Birth: '{candidate.birth_date or 'None'}'", file=sys.stderr)
        
        matched_athlete = find_best_match(
            candidate_athletes,
            target_name=name,
            target_club=club,
            target_birth_date=birth_date,
            expected_category=category,
            competition_year=competition_year,
        )
        
        if self.debug and candidate_athletes:
            print(f"DEBUG: Candidate scores:", file=sys.stderr)
            for candidate in candidate_athletes:
                print(f"  {candidate.name}: {getattr(candidate, 'similarity_score', 'N/A')}", file=sys.stderr)
        
        if not matched_athlete:
            if self.debug:
                print(f"No good match found for {name} (club: {club}, birth: {birth_date}, category: {category})", file=sys.stderr)
            return None
        
        if self.debug:
            print(f"Best match: {matched_athlete.name} (score: {matched_athlete.similarity_score:.2f})", file=sys.stderr)
        
        # Fetch athlete profile and extract PB for event
        if self.debug:
            print(f"Fetching fresh data for athlete {matched_athlete.id}", file=sys.stderr)
        try:
            athlete_profile = self.scraper.fetch_athlete_profile(matched_athlete.id)
        except Exception as e:
            if self.debug:
                print(f"Error fetching profile: {e}", file=sys.stderr)
            return None
        
        if not athlete_profile:
            if self.debug:
                print(f"Could not fetch profile for athlete {matched_athlete.id}", file=sys.stderr)
            return None
        
        # Extract PB for the requested event, passing category for implement weight matching
        pb_result = athlete_profile.get_pb(standardized_event, indoor=False, category=category)
        if not pb_result:
            pb_result = athlete_profile.get_pb(standardized_event, indoor=True, category=category)
        
        if pb_result:
            if self.debug:
                print(f"Found PB: {pb_result}", file=sys.stderr)
        else:
            if self.debug:
                print(f"No PB found for {standardized_event} (category: {category})", file=sys.stderr)
        
        return pb_result
    
    def lookup_athlete(self, name: str, club: str = "", birth_date: str = "") -> Optional[Athlete]:
        """
        Look up a complete athlete profile.
        
        Args:
            name: Athlete's full name
            club: Current or historical club affiliation  
            birth_date: Date of birth in DD.MM.YYYY format
        
        Returns:
            Athlete object with complete profile or None if not found
        """
        surname = extract_surname(name)
        if not surname:
            return None

        try:
            candidate_athletes = self.scraper.search_athletes_by_surname(surname)
        except Exception as e:
            print(f"Error during search: {e}")
            return None
        
        if not candidate_athletes:
            return None
        
        matched_athlete = find_best_match(
            candidate_athletes,
            target_name=name,
            target_club=club,
            target_birth_date=birth_date
        )
        
        if not matched_athlete:
            return None
        
        # Fetch from web
        try:
            athlete_profile = self.scraper.fetch_athlete_profile(matched_athlete.id)
            return athlete_profile
        except Exception as e:
            print(f"Error fetching profile: {e}")
            return None

# Convenience function for simple lookups
def lookup_pb(
    name: str,
    club: str,
    birth_date: str,
    event: str,
    category: str = "",
    competition_year: Optional[int] = None,
    debug: bool = False
) -> Optional[Result]:
    """
    Simple function interface for PB lookup.
    
    Args:
        name: Athlete's full name
        club: Current or historical club affiliation
        birth_date: Date of birth in DD.MM.YYYY format (for disambiguation and age category)
        event: Track and field event (e.g., "100m", "Long Jump", "Shot Put")
        category: Age category like 'J15', 'G12' for validation (optional)
        competition_year: Year of competition for age validation (defaults to current year)
        debug: Enable debug output showing URLs and responses
    
    Returns:
        Result object with PB details or None if no result found
    """
    service = PBLookupService(debug=debug)
    return service.lookup_pb(name, club, birth_date, event, category, competition_year)


def lookup_pb_value(
    name: str,
    club: str,
    birth_date: str,
    event: str,
    category: str = "",
    competition_year: Optional[int] = None,
    debug: bool = False
) -> Optional[float]:
    """
    Simple function interface for PB lookup that returns a float value.
    
    Args:
        name: Athlete's full name
        club: Current or historical club affiliation
        birth_date: Date of birth in DD.MM.YYYY format (for disambiguation and age category)
        event: Track and field event (e.g., "100m", "Long Jump", "Shot Put")
        category: Age category like 'J15', 'G12' for validation (optional)
        competition_year: Year of competition for age validation (defaults to current year)
        debug: Enable debug output showing URLs and responses
    
    Returns:
        PB as a float value or None if no result found
    """
    result = lookup_pb(name, club, birth_date, event, category, competition_year, debug=debug)
    if result:
        return result.get_result_as_float()
    return None
