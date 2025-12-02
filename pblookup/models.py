"""Data models for the PB lookup utility."""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Result:
    """Represents a personal best result for an athlete in a specific event."""
    athlete_name: str
    club: str
    event: str
    result: str  # Time/Distance/Height as string (e.g., "10.54", "6.45", "12,67")
    result_seconds: Optional[float] = None  # Normalized for time events
    result_meters: Optional[float] = None   # Normalized for distance events
    date: Optional[datetime] = None
    venue: Optional[str] = None
    competition: Optional[str] = None
    wind: Optional[str] = None  # For wind-assisted events (e.g., "+1.2", "ok")
    category: Optional[str] = None  # Senior, Junior, Youth, etc.
    season: Optional[int] = None  # Year
    indoor: bool = False
    position: Optional[str] = None  # Final placing or heat info (e.g., "2", "3-h2")

    def __str__(self) -> str:
        wind_info = f" ({self.wind})" if self.wind and self.wind != "ok" else ""
        date_info = f" on {self.date.strftime('%d.%m.%Y')}" if self.date else ""
        venue_info = f" at {self.venue}" if self.venue else ""
        return f"{self.result}{wind_info}{date_info}{venue_info}"

    def get_result_as_float(self) -> Optional[float]:
        """
        Get the result as a float value.
        
        Handles Norwegian locale (comma as decimal separator) and various formats:
        - "4,23" -> 4.23 (field events)
        - "10.54" -> 10.54 (time events)
        - "1:23.45" or "1:23,45" -> 83.45 (time events with minutes)
        
        Returns None if the result cannot be parsed.
        """
        if not self.result:
            return None
            
        try:
            result_str = self.result.strip()
            
            # Handle time format with minutes (e.g., "1:23.45" or "1:23,45")
            if ':' in result_str:
                parts = result_str.split(':')
                if len(parts) == 2:
                    minutes = float(parts[0])
                    seconds = float(parts[1].replace(',', '.'))
                    return minutes * 60 + seconds
                elif len(parts) == 3:
                    # Hours:minutes:seconds (unlikely for athletics PBs)
                    hours = float(parts[0])
                    minutes = float(parts[1])
                    seconds = float(parts[2].replace(',', '.'))
                    return hours * 3600 + minutes * 60 + seconds
            
            # Handle regular decimal (comma or dot)
            return float(result_str.replace(',', '.'))
            
        except (ValueError, AttributeError):
            return None


@dataclass
class Athlete:
    """Represents an athlete with their profile information and records."""
    id: int
    name: str
    birth_date: Optional[str] = None
    clubs: Optional[List[str]] = None  # Historical club affiliations
    outdoor_pbs: Optional[Dict[str, Result]] = None
    indoor_pbs: Optional[Dict[str, Result]] = None
    last_updated: Optional[datetime] = None

    def __post_init__(self):
        if self.clubs is None:
            self.clubs = []
        if self.outdoor_pbs is None:
            self.outdoor_pbs = {}
        if self.indoor_pbs is None:
            self.indoor_pbs = {}

    def get_pb(self, event: str, indoor: bool = False, category: str = "") -> Optional[Result]:
        """Get personal best for a specific event.
        
        Args:
            event: Event name to look up
            indoor: If True, look in indoor PBs
            category: Age category like 'G12', 'J15' for implement weight matching
        """
        from .events import find_best_event_match, standardize_event_name
        
        records = self.indoor_pbs if indoor else self.outdoor_pbs
        if not records:
            return None
        
        # Standardize the target event for comparison
        standardized_event = standardize_event_name(event)
        
        # Try exact match with original event name first
        if event in records:
            return records[event]
            
        # Try exact match with standardized event name
        if standardized_event in records:
            return records[standardized_event]
        
        # Use fuzzy matching for throwing events with implement specifications
        available_events = list(records.keys())
        best_match = find_best_event_match(event, available_events, category=category)
        
        if best_match:
            return records[best_match]
        
        return None

    def add_result(self, result: Result):
        """Add a result to the athlete's records."""
        records = self.indoor_pbs if result.indoor else self.outdoor_pbs
        if records is None:
            return
            
        # Update if this is a new PB or we don't have this event yet
        existing = records.get(result.event)
        if existing is None or self._is_better_result(result, existing):
            records[result.event] = result

    def _is_better_result(self, new_result: Result, existing_result: Result) -> bool:
        """Compare two results to determine if new result is better."""
        # This is a simplified comparison - in reality, we'd need event-specific logic
        # For time events, lower is better; for field events, higher is better
        try:
            new_val = float(new_result.result.replace(',', '.'))
            existing_val = float(existing_result.result.replace(',', '.'))
            
            # Simple heuristic: if event contains "m" and no "meter" in name, it's likely field event
            is_field_event = ('m' in new_result.event.lower() and 
                             'meter' not in new_result.event.lower())
            
            if is_field_event:
                return new_val > existing_val  # Higher is better for field events
            else:
                return new_val < existing_val  # Lower is better for time events
        except (ValueError, AttributeError):
            # If we can't parse, assume new is better (safer for data updates)
            return True


@dataclass
class SearchCandidate:
    """Represents a candidate athlete found during search."""
    id: int
    name: str
    club: Optional[str] = None
    birth_date: Optional[str] = None
    url: Optional[str] = None
    similarity_score: float = 0.0
