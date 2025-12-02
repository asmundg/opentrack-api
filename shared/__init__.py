"""Shared configuration modules for opentrack automation."""
from .implement_weights import (
    IMPLEMENT_WEIGHTS_KG,
    IMPLEMENT_WEIGHTS_DISPLAY,
    THROWING_EVENTS,
    EVENT_CODE_TO_NORWEGIAN,
    NORWEGIAN_TO_EVENT_CODE,
    parse_category,
    get_target_weight_kg,
    get_display_weight,
    extract_weight_from_event_name,
    weight_matches_category,
)

__all__ = [
    "IMPLEMENT_WEIGHTS_KG",
    "IMPLEMENT_WEIGHTS_DISPLAY",
    "THROWING_EVENTS",
    "EVENT_CODE_TO_NORWEGIAN",
    "NORWEGIAN_TO_EVENT_CODE",
    "parse_category",
    "get_target_weight_kg",
    "get_display_weight",
    "extract_weight_from_event_name",
    "weight_matches_category",
]
