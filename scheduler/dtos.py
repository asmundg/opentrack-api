"""
Pydantic DTOs for robust CSV import/export validation.

All CSV I/O goes through these validated DTOs to avoid opaque dictionaries
and ensure data integrity.
"""

from datetime import datetime, time, date
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Self

from .models import EventType, Category, Venue, get_venue_for_event


class EventScheduleRow(BaseModel):
    """
    Represents a single event in the event overview CSV.

    This CSV is used for the manual scheduling step where users can adjust
    event start/end times before regenerating the final schedule.
    """

    event_group_id: str = Field(
        description="Unique identifier for the event group (e.g., '100m_j15-j16')"
    )
    event_type: EventType = Field(
        description="The type of event (e.g., m100, sp, lj)"
    )
    categories: str = Field(
        description="Comma-separated age categories in this group (e.g., 'J15,J16')"
    )
    venue: Venue = Field(
        description="The venue where this event takes place"
    )
    date: date = Field(
        description="Event date (YYYY-MM-DD format)"
    )
    start_time: time = Field(
        description="Event start time (HH:MM format)"
    )
    end_time: time = Field(
        description="Event end time (HH:MM format)"
    )
    duration_minutes: int = Field(
        description="Total duration in minutes",
        ge=0
    )

    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, v: str | date) -> date:
        """Parse date from string if needed."""
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            # Handle YYYY-MM-DD or DD.MM.YYYY format
            try:
                return datetime.strptime(v.strip(), '%Y-%m-%d').date()
            except ValueError:
                try:
                    return datetime.strptime(v.strip(), '%d.%m.%Y').date()
                except ValueError:
                    # Try ISO format
                    return datetime.fromisoformat(v).date()
        raise ValueError(f"Invalid date format: {v}")

    @field_validator('start_time', 'end_time', mode='before')
    @classmethod
    def parse_time(cls, v: str | time) -> time:
        """Parse time from string if needed."""
        if isinstance(v, time):
            return v
        if isinstance(v, str):
            # Handle HH:MM format
            try:
                return datetime.strptime(v.strip(), '%H:%M').time()
            except ValueError:
                # Try ISO format
                return datetime.fromisoformat(v).time()
        raise ValueError(f"Invalid time format: {v}")

    @model_validator(mode='after')
    def validate_time_range(self) -> Self:
        """Ensure end_time is after start_time."""
        if self.end_time <= self.start_time:
            raise ValueError(
                f"end_time ({self.end_time}) must be after start_time ({self.start_time})"
            )

        # Calculate actual duration and check it matches
        start_dt = datetime.combine(datetime.today(), self.start_time)
        end_dt = datetime.combine(datetime.today(), self.end_time)
        actual_minutes = int((end_dt - start_dt).total_seconds() / 60)

        if actual_minutes != self.duration_minutes:
            raise ValueError(
                f"Duration mismatch: start/end times indicate {actual_minutes} minutes "
                f"but duration_minutes is {self.duration_minutes}"
            )

        return self

    def to_csv_dict(self) -> dict[str, str]:
        """Convert to dictionary for CSV writing."""
        return {
            'event_group_id': self.event_group_id,
            'event_type': self.event_type.value,
            'categories': self.categories,
            'venue': self.venue.value,
            'date': self.date.strftime('%Y-%m-%d'),
            'start_time': self.start_time.strftime('%H:%M'),
            'end_time': self.end_time.strftime('%H:%M'),
            'duration_minutes': str(self.duration_minutes),
        }

    @classmethod
    def from_csv_dict(cls, row: dict[str, str]) -> 'EventScheduleRow':
        """Create from CSV row dictionary with validation."""
        # Parse event type - handle both enum name and value
        event_type_str = row['event_type']
        try:
            # Try to find by value first
            event_type = next(et for et in EventType if et.value == event_type_str)
        except StopIteration:
            # Fall back to enum name
            event_type = EventType[event_type_str]

        # Parse venue - handle both enum name and value
        venue_str = row['venue']
        try:
            venue = next(v for v in Venue if v.value == venue_str)
        except StopIteration:
            venue = Venue[venue_str.upper()]

        return cls(
            event_group_id=row['event_group_id'],
            event_type=event_type,
            categories=row['categories'],
            venue=venue,
            date=row['date'],
            start_time=row['start_time'],
            end_time=row['end_time'],
            duration_minutes=int(row['duration_minutes']),
        )


class AthleteScheduleRow(BaseModel):
    """
    Represents a single row in the athlete overview CSV.

    This is the existing Isonen CSV format with added start times.
    """

    # Original Isonen fields
    fornavn: str = Field(description="First name")
    etternavn: str = Field(description="Last name")
    kjonn: str = Field(description="Gender (J/G)")
    klasse: str = Field(description="Age category")
    klubb: str = Field(description="Club name")
    ovelse: str = Field(description="Event name")
    dato: str = Field(description="Date")
    kl: str = Field(description="Start time (HH:MM format)")
    sb: str | None = Field(default=None, description="Season best")
    pb: str | None = Field(default=None, description="Personal best")

    @field_validator('kl', mode='before')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time is in HH:MM format."""
        if not v or v == "":
            raise ValueError("Start time (kl) cannot be empty")

        try:
            # Parse to validate format
            datetime.strptime(v.strip(), '%H:%M')
            return v.strip()
        except ValueError:
            raise ValueError(f"Invalid time format: {v}. Expected HH:MM")

    def to_csv_dict(self) -> dict[str, str]:
        """Convert to dictionary for CSV writing."""
        return {
            'Fornavn': self.fornavn,
            'Etternavn': self.etternavn,
            'Kjønn': self.kjonn,
            'Klasse': self.klasse,
            'Klubb': self.klubb,
            'Øvelse': self.ovelse,
            'Dato': self.dato,
            'Kl.': self.kl,
            'SB': self.sb or '',
            'PB': self.pb or '',
        }
