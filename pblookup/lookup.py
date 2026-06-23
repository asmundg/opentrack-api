"""Main PB lookup functionality."""
import sys
from typing import Optional

from .models import Result, Athlete
from .scraper import MinfriidrettsScraper
from .matching import extract_surname, find_best_match
from .events import standardize_event_name, better_result


class PBLookupService:
    """Service for looking up Personal Bests of Norwegian track and field athletes."""
    
    def __init__(self, debug: bool = False):
        self.scraper = MinfriidrettsScraper(debug=debug)
        self.debug = debug
        
    def _find_match(
        self,
        name: str,
        club: str,
        birth_date: str,
        category: str = "",
        competition_year: Optional[int] = None,
    ):
        """Search by surname and return the best-matching candidate, or None.

        Shared by the PB and SB lookups so the search/match (the rate-limited,
        expensive part) happens once per athlete-event regardless of how many
        performance views are read afterwards.
        """
        surname = extract_surname(name)
        if not surname:
            if self.debug:
                print(f"Could not extract surname from '{name}'", file=sys.stderr)
            return None

        if self.debug:
            print(f"Searching for athletes with surname '{surname}'", file=sys.stderr)

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

        return matched_athlete

    def _result_for_view(
        self, athlete_id: int, standardized_event: str, category: str, view: str
    ) -> Optional[Result]:
        """Fetch one profile view and return its result for the event, or None."""
        if self.debug:
            print(f"Fetching {view} data for athlete {athlete_id}", file=sys.stderr)
        try:
            profile = self.scraper.fetch_athlete_profile(athlete_id, view=view)
        except Exception as e:
            if self.debug:
                print(f"Error fetching profile: {e}", file=sys.stderr)
            return None

        if not profile:
            if self.debug:
                print(f"Could not fetch {view} profile for athlete {athlete_id}", file=sys.stderr)
            return None

        # Take the genuine best across the outdoor and indoor records: the
        # source's indoor/outdoor split is unreliable, and an athlete's best in
        # an event may sit on either side (e.g. an indoor high jump beating the
        # outdoor mark).
        outdoor = profile.get_pb(standardized_event, indoor=False, category=category)
        indoor = profile.get_pb(standardized_event, indoor=True, category=category)
        result = better_result(standardized_event, outdoor, indoor)

        if self.debug:
            if result:
                print(f"Found {view}: {result}", file=sys.stderr)
            else:
                print(f"No {view} found for {standardized_event} (category: {category})", file=sys.stderr)
        return result

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
        standardized_event = standardize_event_name(event)
        matched_athlete = self._find_match(
            name, club, birth_date, category, competition_year
        )
        if not matched_athlete:
            return None
        return self._result_for_view(
            matched_athlete.id, standardized_event, category, "PR"
        )

    def lookup_pb_sb(
        self,
        name: str,
        club: str,
        birth_date: str,
        event: str,
        category: str = "",
        competition_year: Optional[int] = None,
    ) -> tuple[Optional[Result], Optional[Result]]:
        """Look up an athlete's all-time PB and current-season SB for an event.

        Matches the athlete once, then reads both the all-time (PR) and
        season-best (SB) profile views. Returns ``(pb, sb)``; either may be None
        when the athlete has no such result.
        """
        standardized_event = standardize_event_name(event)
        matched_athlete = self._find_match(
            name, club, birth_date, category, competition_year
        )
        if not matched_athlete:
            return None, None
        pb = self._result_for_view(
            matched_athlete.id, standardized_event, category, "PR"
        )
        sb = self._result_for_view(
            matched_athlete.id, standardized_event, category, "SB"
        )
        return pb, sb
    
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
