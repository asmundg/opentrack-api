"""
Type definitions for the track meet scheduler.

This module contains shared type definitions used across the scheduler modules.
"""

from dataclasses import dataclass
from typing import Any

from .models import EventGroup, Athlete

@dataclass(frozen=True)
class SchedulingResult:
    """Complete scheduling result with events, athletes, and solution."""

    status: str
    schedule: dict[int, list[dict[str, Any]]]
    total_slots: int
    total_duration_minutes: int
    slot_duration_minutes: int
    events_per_slot: dict[int, int]
    slots_with_events: int
    optimization_stats: dict[str, Any] | None
    events: list[EventGroup]
    athletes: list[Athlete]