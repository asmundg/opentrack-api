"""Implement weight configuration for throwing events.

This module contains the official implement weights used in Norwegian athletics,
shared between opentrack_admin and pblookup modules.
"""

import re
from typing import Optional

# Throwing implement weights by category and event
# Format: {event_code: {gender: {age: weight_kg}}}
# Gender: "G" for boys/men, "J" for girls/women
# Only transition ages are listed — the lookup functions find the closest bracket.
# Age groups: 10 (rekrutt/6-10), 11+, 20 (U20), 23 (U23), 99 (Senior)
# Note: DT, JT, HT start at age 11 (not offered for rekrutt/10)
# Weights are in kg (float)
IMPLEMENT_WEIGHTS_KG = {
    "SP": {  # Kule (Shot Put)
        "G": {
            10: 2.0,
            12: 3.0,
            14: 4.0,
            16: 5.0,
            18: 6.0,
            20: 7.26,
            50: 6,
            60: 5,
            70: 4,
            80: 3,
        },
        "J": {10: 2.0, 14: 3.0, 18: 4.0, 50: 3, 75: 2},
    },
    "DT": {  # Diskos (Discus) - starts at 11
        "G": {11: 0.6, 12: 0.75, 14: 1.0, 16: 1.5, 18: 1.75, 20: 2.0, 50: 1.5, 60: 1},
        "J": {11: 0.6, 14: 0.75, 16: 1.0, 75: 0.75},
    },
    "HT": {  # Slegge (Hammer) - starts at 11
        "G": {11: 2.0, 13: 3.0, 14: 4.0, 16: 5.0, 18: 6.0, 20: 7.26, 50: 6, 60: 5, 70: 4, 80: 3},
        "J": {11: 2.0, 14: 3.0, 18: 4.0, 50: 3, 75: 2},
    },
    "JT": {  # Spyd (Javelin) - starts at 11
        "G": {11: 0.4, 14: 0.6, 16: 0.7, 18: 0.8, 50: 0.7, 60: 0.6, 70: 0.5, 80: 0.4},
        "J": {11: 0.4, 15: 0.5, 18: 0.6, 50: 0.5, 75: 0.4},
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
    match = re.match(r"^([GJ])(\d+)$", category, re.IGNORECASE)
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

    # Find the last bracket where key <= age
    available_ages = sorted(gender_weights.keys())
    if not available_ages:
        return None

    result = None
    for bracket_age in available_ages:
        if bracket_age <= age:
            result = gender_weights[bracket_age]
        else:
            break

    return result


def _format_weight(weight_kg: float, event_code: str) -> str:
    """Format a weight in kg as a Norwegian display string.

    Javelin uses grams with 'g' suffix (e.g. "400g").
    Others use kg with comma decimal (e.g. "2", "0,75", "7,26").
    """
    if event_code == "JT":
        return f"{int(weight_kg * 1000)}g"
    if weight_kg == int(weight_kg):
        return str(int(weight_kg))
    return f"{weight_kg:.2f}".rstrip("0").replace(".", ",")


def get_display_weight(event_code: str, category: str) -> Optional[str]:
    """Get the display format weight for a throwing event and category.

    Args:
        event_code: Event code (SP, DT, HT, JT)
        category: Category like "G10", "J15", "M", "W"

    Returns:
        Weight string in display format (e.g., "2", "0,75", "400g") or None
    """
    weight_kg = get_target_weight_kg(event_code, category)
    if weight_kg is None:
        return None
    return _format_weight(weight_kg, event_code)


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
    kg_match = re.search(r"(\d+[,.]?\d*)\s*kg", event_lower)
    if kg_match:
        weight_str = kg_match.group(1).replace(",", ".")
        return float(weight_str)

    # Match gram patterns: "600gram", "400g"
    gram_match = re.search(r"(\d+)\s*(?:gram|g)\b", event_lower)
    if gram_match:
        return float(gram_match.group(1)) / 1000

    return None


def weight_matches_category(
    event_name: str, event_code: str, category: str, tolerance: float = 0.1
) -> bool:
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
