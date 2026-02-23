"""Event name mappings and standardization."""
import re
from typing import Dict, Set, List, Optional

from shared.implement_weights import (
    extract_weight_from_event_name,
    get_target_weight_kg,
    NORWEGIAN_TO_EVENT_CODE,
)
from shared.hurdle_heights import (
    extract_height_from_event_name,
    get_target_height_cm,
    HURDLE_EVENTS,
)

# Event name mappings from various formats to standardized names
EVENT_MAPPINGS: Dict[str, str] = {
    # Norwegian to English track events
    "100 meter": "100m",
    "200 meter": "200m", 
    "400 meter": "400m",
    "600 meter": "600m",
    "800 meter": "800m",
    "1500 meter": "1500m",
    "3000 meter": "3000m",
    "5000 meter": "5000m",
    "10000 meter": "10000m",
    "110 meter hekk": "110m_hurdles",
    "100 meter hekk": "100m_hurdles",
    "400 meter hekk": "400m_hurdles",
    "3000 meter hinder": "3000m_steeplechase",
    
    # Norwegian field events
    "lengde": "long_jump",
    "høyde": "high_jump", 
    "stav": "pole_vault",
    "tresteg": "triple_jump",
    "kule": "shot_put",
    "diskos": "discus",
    "slegge": "hammer",
    "spyd": "javelin",
    
    # Indoor events
    "60 meter": "60m",
    "60 meter hekk": "60m_hurdles",
    "200 meter innendørs": "200m_indoor",
    "400 meter innendørs": "400m_indoor",
    "600 meter innendørs": "600m_indoor",
    "800 meter innendørs": "800m_indoor",
    "1500 meter innendørs": "1500m_indoor",
    "3000 meter innendørs": "3000m_indoor",
    
    # Handle variations and common formats
    "100m": "100m",
    "100 m": "100m",
    "100meter": "100m",
    "200m": "200m",
    "200 m": "200m", 
    "400m": "400m",
    "400 m": "400m",
    "600m": "600m",
    "600 m": "600m",
    "800m": "800m",
    "800 m": "800m",
    "1500m": "1500m",
    "1500 m": "1500m",
    
    # Field event variations
    "long jump": "long_jump",
    "high jump": "high_jump",
    "pole vault": "pole_vault",
    "triple jump": "triple_jump", 
    "shot put": "shot_put",
    "discus throw": "discus",
    "hammer throw": "hammer",
    "hammer": "hammer",
    "javelin throw": "javelin",
    
    # Hurdles variations
    "110m hurdles": "110m_hurdles",
    "100m hurdles": "100m_hurdles", 
    "400m hurdles": "400m_hurdles",
    "60m hurdles": "60m_hurdles",
    
    # Steeplechase
    "3000m steeplechase": "3000m_steeplechase",
    "steeplechase": "3000m_steeplechase",
}

# Events where lower values are better (time events)
TIME_EVENTS: Set[str] = {
    "60m", "100m", "200m", "400m", "600m", "800m", "1500m", "3000m", "5000m", "10000m",
    "60m_hurdles", "100m_hurdles", "110m_hurdles", "400m_hurdles",
    "3000m_steeplechase", "marathon", "half_marathon", "10k", "5k",
    "200m_indoor", "400m_indoor", "600m_indoor", "800m_indoor", "1500m_indoor", "3000m_indoor"
}

# Events where higher values are better (field events)  
FIELD_EVENTS: Set[str] = {
    "long_jump", "high_jump", "pole_vault", "triple_jump",
    "shot_put", "discus", "hammer", "javelin"
}

# Events that can have wind measurements
WIND_EVENTS: Set[str] = {
    "100m", "200m", "100m_hurdles", "110m_hurdles", "long_jump", "triple_jump"
}

# Throwing events that often have implement weight/size specifications
THROWING_EVENTS_WITH_IMPLEMENTS: Dict[str, List[str]] = {
    "hammer": ["slegge"],
    "shot_put": ["kule"],
    "discus": ["diskos"],
    "javelin": ["spyd"]
}


def extract_base_event_name(event: str) -> str:
    """Extract base event name, removing implement specifications."""
    event_lower = event.lower().strip()
    
    # Remove common implement specifications
    # Examples: "Slegge 3,0Kg (119,5cm)" -> "slegge"
    #          "Kule 2,0kg" -> "kule"
    #          "Diskos 600gram" -> "diskos"
    #          "Spyd 400gram" -> "spyd"
    
    # Remove weight/size specifications (kg, gram, cm, etc.)
    base_event = re.sub(r'\s+\d+[,.]?\d*\s*(kg|gram|g|cm|m)\b.*$', '', event_lower, flags=re.IGNORECASE)
    base_event = re.sub(r'\s+\([^)]+\)$', '', base_event)  # Remove parentheses content
    
    return base_event.strip()


def _get_event_code_from_name(event_name: str) -> Optional[str]:
    """Get event code (SP, DT, HT, JT) from event name."""
    base = extract_base_event_name(event_name)
    return NORWEGIAN_TO_EVENT_CODE.get(base)


def find_best_event_match(
    target_event: str,
    available_events: List[str],
    category: str = ""
) -> Optional[str]:
    """
    Find the best matching event from available events.
    
    For throwing events with implement specifications, finds the closest match
    based on the base event name and category-appropriate implement weight.
    
    Args:
        target_event: The event we're looking for (e.g., "slegge", "hammer", "shot_put")
        available_events: List of actual events available for the athlete
        category: Age category like 'G12', 'J15' for weight matching (optional)
        
    Returns:
        The best matching event name, or None if no good match found
    """
    if not available_events:
        return None
        
    # Standardize the target event
    standardized_target = standardize_event_name(target_event)
    base_target = extract_base_event_name(target_event)
    
    # Look for exact matches first (only exact string matches, not standardized)
    for event in available_events:
        if event.lower().strip() == target_event.lower().strip():
            return event
    
    # Look for all matching events (standardized and base event matches)
    throwing_matches = []
    for event in available_events:
        base_event = extract_base_event_name(event)
        
        # Check if standardized events match
        if standardize_event_name(event) == standardized_target:
            throwing_matches.append(event)
        # Check if base events match
        elif base_event == base_target:
            throwing_matches.append(event)
        elif standardize_event_name(base_event) == standardized_target:
            throwing_matches.append(event)
        
        # Also check reverse mappings for Norwegian events
        for std_event, variants in THROWING_EVENTS_WITH_IMPLEMENTS.items():
            if standardized_target == std_event and base_event in variants:
                throwing_matches.append(event)
            elif base_target in variants and base_event in variants:
                throwing_matches.append(event)
    
    if not throwing_matches:
        return None
    
    # Remove duplicates while preserving order
    throwing_matches = list(dict.fromkeys(throwing_matches))
    
    # If we have only one match, return it
    if len(throwing_matches) == 1:
        return throwing_matches[0]
    
    # Get the event code for target weight lookup
    event_code = _get_event_code_from_name(target_event)
    target_weight = None
    if event_code and category:
        target_weight = get_target_weight_kg(event_code, category)
    
    if target_weight is not None:
        # Sort by closeness to the target weight for the category
        def weight_distance(event_name: str) -> float:
            """Calculate distance from target weight (lower is better)."""
            weight = extract_weight_from_event_name(event_name)
            if weight is None:
                return float('inf')  # No weight info, deprioritize
            return abs(weight - target_weight)

        throwing_matches.sort(key=weight_distance)
        return throwing_matches[0]

    # Check if this is a hurdle event with height specifications
    target_height = None
    if standardized_target in HURDLE_EVENTS and category:
        target_height = get_target_height_cm(standardized_target, category)

    if target_height is not None:
        def height_distance(event_name: str) -> float:
            height = extract_height_from_event_name(event_name)
            if height is None:
                return float('inf')
            return abs(height - target_height)

        throwing_matches.sort(key=height_distance)
        return throwing_matches[0]

    # No category provided - fall back to preferring heavier implements (senior weights)
    # or taller hurdles
    def get_weight_or_height(event_name: str) -> float:
        """Extract weight/height for sorting (higher is better for seniors)."""
        weight = extract_weight_from_event_name(event_name)
        if weight is not None:
            return weight
        height = extract_height_from_event_name(event_name)
        if height is not None:
            return height
        return 0.0

    throwing_matches.sort(key=get_weight_or_height, reverse=True)
    return throwing_matches[0]


def standardize_event_name(event: str) -> str:
    """Convert event name to standardized format."""
    # First try direct mapping
    event_lower = event.lower().strip()
    if event_lower in EVENT_MAPPINGS:
        return EVENT_MAPPINGS[event_lower]
    
    # For throwing events, extract base event and map
    base_event = extract_base_event_name(event)
    if base_event in EVENT_MAPPINGS:
        return EVENT_MAPPINGS[base_event]
    
    return event_lower


def is_time_event(event: str) -> bool:
    """Check if event is a time-based event (lower is better)."""
    standardized = standardize_event_name(event)
    return standardized in TIME_EVENTS


def is_field_event(event: str) -> bool:
    """Check if event is a field event (higher is better)."""
    standardized = standardize_event_name(event)
    return standardized in FIELD_EVENTS


def can_have_wind(event: str) -> bool:
    """Check if event can have wind measurements."""
    standardized = standardize_event_name(event)
    return standardized in WIND_EVENTS


def is_indoor_event(event: str) -> bool:
    """Check if event name indicates indoor competition."""
    return "innendørs" in event.lower() or "indoor" in event.lower() or event.lower() in ["60m", "60 meter", "60m_hurdles", "60 meter hekk"]
