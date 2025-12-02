"""Implement weight configuration for throwing events.

This module contains the official implement weights used in Norwegian athletics,
shared between opentrack_admin and pblookup modules.
"""
import re
from typing import Optional

# Throwing implement weights by category and event
# Format: {event_code: {gender: {age: weight_kg}}}
# Gender: "G" for boys/men, "J" for girls/women
# Age groups: 10 (rekrutt/6-10), 11, 12, 13, 14, 15, 16, 17, 20 (U20), 23 (U23), 99 (Senior)
# Note: DT, JT, HT start at age 11 (not offered for rekrutt/10)
# Weights are in kg (float) for comparison purposes
IMPLEMENT_WEIGHTS_KG = {
    "SP": {  # Kule (Shot Put)
        "G": {10: 2.0, 11: 2.0, 12: 3.0, 13: 3.0, 14: 4.0, 15: 4.0, 16: 5.0, 17: 5.0, 20: 6.0, 23: 7.26, 99: 7.26},
        "J": {10: 2.0, 11: 2.0, 12: 2.0, 13: 2.0, 14: 3.0, 15: 3.0, 16: 3.0, 17: 3.0, 20: 4.0, 23: 4.0, 99: 4.0},
    },
    "DT": {  # Diskos (Discus) - starts at 11
        "G": {11: 0.6, 12: 0.75, 13: 0.75, 14: 1.0, 15: 1.0, 16: 1.5, 17: 1.5, 20: 1.75, 23: 2.0, 99: 2.0},
        "J": {11: 0.6, 12: 0.6, 13: 0.6, 14: 0.75, 15: 0.75, 16: 1.0, 17: 1.0, 20: 1.0, 23: 1.0, 99: 1.0},
    },
    "HT": {  # Slegge (Hammer) - starts at 11
        "G": {11: 2.0, 12: 2.0, 13: 3.0, 14: 4.0, 15: 4.0, 16: 5.0, 17: 5.0, 20: 7.26, 23: 7.26, 99: 7.26},
        "J": {11: 2.0, 12: 2.0, 13: 2.0, 14: 3.0, 15: 3.0, 16: 3.0, 17: 3.0, 20: 4.0, 23: 4.0, 99: 4.0},
    },
    "JT": {  # Spyd (Javelin) - starts at 11, weights in kg
        "G": {11: 0.4, 12: 0.4, 13: 0.4, 14: 0.6, 15: 0.6, 16: 0.7, 17: 0.7, 20: 0.8, 23: 0.8, 99: 0.8},
        "J": {11: 0.4, 12: 0.4, 13: 0.4, 14: 0.4, 15: 0.4, 16: 0.5, 17: 0.5, 20: 0.5, 23: 0.6, 99: 0.6},
    },
}

# Display format weights (Norwegian format with comma decimal)
IMPLEMENT_WEIGHTS_DISPLAY = {
    "SP": {  # Kule (Shot Put)
        "G": {10: "2", 11: "2", 12: "3", 13: "3", 14: "4", 15: "4", 16: "5", 17: "5", 20: "6", 23: "7,26", 99: "7,26"},
        "J": {10: "2", 11: "2", 12: "2", 13: "2", 14: "3", 15: "3", 16: "3", 17: "3", 20: "4", 23: "4", 99: "4"},
    },
    "DT": {  # Diskos (Discus)
        "G": {11: "0,6", 12: "0,75", 13: "0,75", 14: "1", 15: "1", 16: "1,5", 17: "1,5", 20: "1,75", 23: "2", 99: "2"},
        "J": {11: "0,6", 12: "0,6", 13: "0,6", 14: "0,75", 15: "0,75", 16: "1", 17: "1", 20: "1", 23: "1", 99: "1"},
    },
    "HT": {  # Slegge (Hammer)
        "G": {11: "2", 12: "2", 13: "3", 14: "4", 15: "4", 16: "5", 17: "5", 20: "7,26", 23: "7,26", 99: "7,26"},
        "J": {11: "2", 12: "2", 13: "2", 14: "3", 15: "3", 16: "3", 17: "3", 20: "4", 23: "4", 99: "4"},
    },
    "JT": {  # Spyd (Javelin)
        "G": {11: "400g", 12: "400g", 13: "400g", 14: "600g", 15: "600g", 16: "700g", 17: "700g", 20: "800g", 23: "800g", 99: "800g"},
        "J": {11: "400g", 12: "400g", 13: "400g", 14: "400g", 15: "400g", 16: "500g", 17: "500g", 20: "500g", 23: "600g", 99: "600g"},
    },
}

# Events that use implement weights
THROWING_EVENTS = {"SP", "DT", "HT", "JT"}

# Event code to Norwegian name mapping
EVENT_CODE_TO_NORWEGIAN = {
    "SP": "kule",
    "DT": "diskos",
    "HT": "slegge",
    "JT": "spyd",
}

# Norwegian name to event code mapping
NORWEGIAN_TO_EVENT_CODE = {
    "kule": "SP",
    "diskos": "DT",
    "slegge": "HT",
    "spyd": "JT",
    "shot": "SP",
    "shot put": "SP",
    "discus": "DT",
    "hammer": "HT",
    "javelin": "JT",
}


def parse_category(category: str) -> tuple[Optional[str], Optional[int]]:
    """Parse category string into gender and age.
    
    Args:
        category: Category like "G10", "J15", "M", "W", "U20", "G-rekrutt"
        
    Returns:
        Tuple of (gender, age) where gender is "G" or "J", age is int or None
    """
    if not category:
        return None, None
    
    category = category.strip()
    
    # Handle rekrutt categories
    if category.lower().endswith("-rekrutt"):
        prefix = category[0].upper()
        if prefix in ("G", "J"):
            return prefix, 10
        return None, None
    
    # Handle G/J + age (e.g., G10, J15)
    match = re.match(r'^([GJ])(\d+)$', category, re.IGNORECASE)
    if match:
        return match.group(1).upper(), int(match.group(2))
    
    # Handle senior categories
    if category.upper() in ("M", "MENN", "MEN"):
        return "G", 99
    if category.upper() in ("W", "K", "KVINNER", "WOMEN"):
        return "J", 99
    if category.upper() == "U20":
        return None, 20  # Gender unknown
    if category.upper() == "U23":
        return None, 23  # Gender unknown
    
    return None, None


def get_target_weight_kg(event_code: str, category: str) -> Optional[float]:
    """Get the target implement weight in kg for a throwing event and category.
    
    Args:
        event_code: Event code (SP, DT, HT, JT)
        category: Category like "G10", "J15", "M", "W"
        
    Returns:
        Weight in kg (float) or None if not determinable
    """
    if event_code not in THROWING_EVENTS:
        return None
    
    gender, age = parse_category(category)
    if gender is None or age is None:
        return None
    
    event_weights = IMPLEMENT_WEIGHTS_KG.get(event_code, {})
    gender_weights = event_weights.get(gender, {})
    
    # Find the appropriate age bracket
    if age in gender_weights:
        return gender_weights[age]
    
    # Find closest age bracket
    available_ages = sorted(gender_weights.keys())
    if not available_ages:
        return None
    
    # Find closest age
    for bracket_age in available_ages:
        if age <= bracket_age:
            return gender_weights[bracket_age]
    
    # Use highest age bracket if older than all
    return gender_weights[available_ages[-1]]


def get_display_weight(event_code: str, category: str) -> Optional[str]:
    """Get the display format weight for a throwing event and category.
    
    Args:
        event_code: Event code (SP, DT, HT, JT)
        category: Category like "G10", "J15", "M", "W"
        
    Returns:
        Weight string in display format (e.g., "2", "0,75", "400g") or None
    """
    if event_code not in THROWING_EVENTS:
        return None
    
    gender, age = parse_category(category)
    if gender is None or age is None:
        return None
    
    event_weights = IMPLEMENT_WEIGHTS_DISPLAY.get(event_code, {})
    gender_weights = event_weights.get(gender, {})
    
    if age in gender_weights:
        return gender_weights[age]
    
    # Find closest age bracket
    available_ages = sorted(gender_weights.keys())
    if not available_ages:
        return None
    
    for bracket_age in available_ages:
        if age <= bracket_age:
            return gender_weights[bracket_age]
    
    return gender_weights[available_ages[-1]]


def extract_weight_from_event_name(event_name: str) -> Optional[float]:
    """Extract implement weight in kg from an event name.
    
    Examples:
        "Kule 2,0kg" -> 2.0
        "Kule 3kg" -> 3.0
        "Diskos 600gram" -> 0.6
        "Spyd 400g" -> 0.4
        "Slegge 3,0Kg (119,5cm)" -> 3.0
        
    Returns:
        Weight in kg (float) or None if not found
    """
    event_lower = event_name.lower()
    
    # Match kg patterns: "3,0kg", "7.26kg", "2kg"
    kg_match = re.search(r'(\d+[,.]?\d*)\s*kg', event_lower)
    if kg_match:
        weight_str = kg_match.group(1).replace(',', '.')
        return float(weight_str)
    
    # Match gram patterns: "600gram", "400g"
    gram_match = re.search(r'(\d+)\s*(?:gram|g)\b', event_lower)
    if gram_match:
        return float(gram_match.group(1)) / 1000
    
    return None


def weight_matches_category(event_name: str, event_code: str, category: str, tolerance: float = 0.1) -> bool:
    """Check if the weight in an event name matches the expected weight for a category.
    
    Args:
        event_name: Event name with weight spec (e.g., "Kule 3,0kg")
        event_code: Event code (SP, DT, HT, JT)
        category: Category like "G12", "J15"
        tolerance: Allowed weight difference in kg (default 0.1)
        
    Returns:
        True if weight matches expected weight for category, False otherwise
    """
    target_weight = get_target_weight_kg(event_code, category)
    if target_weight is None:
        return False
    
    actual_weight = extract_weight_from_event_name(event_name)
    if actual_weight is None:
        return False
    
    return abs(actual_weight - target_weight) <= tolerance
