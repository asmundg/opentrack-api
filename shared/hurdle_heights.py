"""Hurdle height configuration by age category.

This module contains the official hurdle heights used in Norwegian athletics,
shared between scheduler and pblookup modules.

Source: Norwegian Athletics Federation hurdle setup tables.
"""
import re
from typing import Optional

from .implement_weights import parse_category

# Hurdle heights in cm by event distance, gender and age.
# Format: {distance_key: {gender: {age: height_cm}}}
# Gender: "G" for boys/men, "J" for girls/women
# Age groups match implement_weights convention.
HURDLE_HEIGHTS_CM = {
    "60m_hurdles": {
        "G": {11: 68, 12: 76.2, 13: 76.2, 14: 84, 15: 84, 16: 91.4, 17: 91.4, 20: 100, 23: 106.7, 99: 106.7},
        "J": {11: 68, 12: 68, 13: 68, 14: 76.2, 15: 76.2, 16: 76.2, 17: 76.2, 20: 84, 23: 84, 99: 84},
    },
    "100m_hurdles": {
        "J": {15: 76.2, 16: 76.2, 17: 76.2, 20: 84, 23: 84, 99: 84},
    },
    "110m_hurdles": {
        "G": {16: 91.4, 17: 91.4, 20: 100, 23: 106.7, 99: 106.7},
    },
}

# Standardized event names that are hurdle events
HURDLE_EVENTS = frozenset(HURDLE_HEIGHTS_CM.keys())


def get_target_height_cm(event: str, category: str) -> Optional[float]:
    """Get the target hurdle height in cm for an event and category.

    Args:
        event: Standardized event name (e.g. "60m_hurdles")
        category: Category like "G12", "J15", "M", "W"

    Returns:
        Height in cm or None if not determinable.
    """
    if event not in HURDLE_HEIGHTS_CM:
        return None

    gender, age = parse_category(category)
    if gender is None or age is None:
        return None

    gender_heights = HURDLE_HEIGHTS_CM[event].get(gender, {})
    if not gender_heights:
        return None

    if age in gender_heights:
        return gender_heights[age]

    # Find closest age bracket
    available_ages = sorted(gender_heights.keys())
    for bracket_age in available_ages:
        if age <= bracket_age:
            return gender_heights[bracket_age]

    return gender_heights[available_ages[-1]]


def extract_height_from_event_name(event_name: str) -> Optional[float]:
    """Extract hurdle height in cm from an event name.

    Examples:
        "60 meter hekk (76,2cm)" -> 76.2
        "60 meter hekk (68,0cm)" -> 68.0
        "110 meter hekk (106.7cm)" -> 106.7

    Returns:
        Height in cm or None if not found.
    """
    match = re.search(r'\((\d+[,.]?\d*)\s*cm\)', event_name, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(',', '.'))
    return None
