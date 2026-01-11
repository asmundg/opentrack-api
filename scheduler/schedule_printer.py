"""
Schedule printing and formatting utilities.

This module contains functions for formatting and printing track meet schedules
in a readable format with emojis and time stamps.
"""

from .functional_scheduler import SchedulingResult


def format_schedule_for_printing(result: SchedulingResult) -> str:
    """Format a schedule for readable printing using the same format as the final output."""
    if result.status != "solved" or not result.schedule:
        return "No events scheduled"
    
    lines: list[str] = []
    lines.append(f"Total time slots used: {result.total_slots}")
    lines.append(f"Total duration: {result.total_duration_minutes} minutes")
    lines.append("-" * 80)
    
    schedule = result.schedule
    slot_duration_minutes = result.slot_duration_minutes
    
    for slot in sorted(schedule.keys()):
        slot_events = schedule[slot]
        start_time_minutes = slot * slot_duration_minutes
        
        # Format time (assuming 9:00 AM start like in the final output)
        start_hour = 9
        total_minutes = start_hour * 60 + start_time_minutes
        hours = total_minutes // 60
        minutes = total_minutes % 60
        time_str = f"{hours}:{minutes:02d}"
        
        # Build event descriptions
        event_descriptions: list[str] = []
        for event_info in slot_events:
            event = event_info['event']
            if event_info['is_start']:
                emoji = "🟢"
                description = f"{event.event_type.value} {event.age_category.value} (START)"
            else:
                emoji = "🔵"
                slot_num = event_info['slot_offset'] + 1  # +1 because we want "slot 2", "slot 3", etc.
                description = f"{event.event_type.value} {event.age_category.value} (slot {slot_num})"
            
            event_descriptions.append(f"{emoji} {description}")
        
        events_str = ", ".join(event_descriptions)
        lines.append(f"Slot {slot:2d} ({time_str}): {events_str}")
    
    return "\n".join(lines)


def print_schedule(
    result: SchedulingResult,
    title: str = "Schedule",
) -> None:
    """Print a formatted schedule with a title."""
    print(f"\n📅 {title}")
    print(format_schedule_for_printing(result))
