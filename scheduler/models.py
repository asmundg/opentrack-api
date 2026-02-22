from dataclasses import dataclass
from enum import Enum


class Venue(Enum):
    """Different venues/facilities at the track meet"""

    TRACK = "track"
    THROWING_CIRCLE = "throwing_circle"
    SHOT_PUT_CIRCLE = "shot_put_circle"
    SHOT_PUT_CIRCLE_2 = "shot_put_circle_2"  # Secondary circle for young athletes
    JUMPING_PIT = "jumping_pit"
    HIGH_JUMP_AREA = "high_jump_area"
    HIGH_JUMP_AREA_2 = "high_jump_area_2"  # Secondary area for young athletes
    JAVELIN_AREA = "javelin_area"


class EventType(Enum):
    m60 = "60m"
    m100 = "100m"
    m200 = "200m"
    m400 = "400m"
    m800 = "800m"
    m1500 = "1500m"
    m5000 = "5000m"
    m60_hurdles = "60m hekk"
    m80_hurdles = "80m hekk"
    m100_hurdles = "100m hekk"
    sp = "Kule"
    lj = "Lengde"
    tj = "Tresteg"
    hj = "Høyde"
    dt = "Diskos"
    jt = "Spyd"
    ht = "Slegge"
    bt = "Liten ball"
    pv = "Stavsprang"


class Category(Enum):
    j10 = "J-Rekrutt"
    j11 = "J11"
    j12 = "J12"
    j13 = "J13"
    j14 = "J14"
    j15 = "J15"
    j16 = "J16"
    j17 = "J17"
    j18_19 = "J18-19"
    g10 = "G-Rekrutt"
    g11 = "G11"
    g12 = "G12"
    g13 = "G13"
    g14 = "G14"
    g15 = "G15"
    g16 = "G16"
    g17 = "G17"
    g18_19 = "G18-19"
    ks = "Kvinner Senior"
    ms = "Menn Senior"
    # Special category for non-athletic events (breaks, etc.) - shown in schedule but ignored for opentrack
    fifa = "FIFA"


# Categories for 10 year olds - HIGHEST priority to finish early
YOUNGEST_CATEGORIES: frozenset[Category] = frozenset(
    {
        Category.j10,
        Category.g10,
    }
)

# Categories for young athletes (10/11/12 year olds) who should finish early
YOUNG_CATEGORIES: frozenset[Category] = frozenset(
    {
        Category.j10,
        Category.g10,
        Category.j11,
        Category.g11,
        Category.j12,
        Category.g12,
    }
)


def is_youngest_category(category: Category) -> bool:
    """Check if a category is for 10 year olds (highest priority to finish early)."""
    return category in YOUNGEST_CATEGORIES


def is_young_category(category: Category) -> bool:
    """Check if a category is for young athletes (10/11/12) who should finish early."""
    return category in YOUNG_CATEGORIES


# Age ordering for categories (lower number = younger)
CATEGORY_AGE_ORDER: dict[Category, int] = {
    Category.j10: 10,
    Category.g10: 10,
    Category.j11: 11,
    Category.g11: 11,
    Category.j12: 12,
    Category.g12: 12,
    Category.j13: 13,
    Category.g13: 13,
    Category.j14: 14,
    Category.g14: 14,
    Category.j15: 15,
    Category.g15: 15,
    Category.j16: 16,
    Category.g16: 16,
    Category.j17: 17,
    Category.g17: 17,
    Category.j18_19: 18,
    Category.g18_19: 18,
    Category.ks: 99,
    Category.ms: 99,  # Seniors last
}


def get_category_age_order(category: Category) -> int:
    """Get the age ordering value for a category (lower = younger)."""
    return CATEGORY_AGE_ORDER.get(category, 99)


# Track event distance ordering (order in which they run)
# Based on physical starting positions as starter team moves counter-clockwise
# (running direction) around the track. Positions are by distance-to-goal:
# 1. 60m/100m - near finish line on main straight (60m, 100m to goal)
# 2. 200m/5000m - at 200m-to-goal position (5000m = 12×400 + 200)
# 3. 1500m - at 300m-to-goal position (1500m = 3×400 + 300)
# 4. 400m/800m - at finish line (full laps)
TRACK_DISTANCE_ORDER: list[EventType] = [
    EventType.m60,
    EventType.m60_hurdles,
    EventType.m80_hurdles,  # 80m hurdles after 60m block
    EventType.m100,
    EventType.m100_hurdles,
    EventType.m200,  # 200m to goal
    EventType.m5000,  # 200m to goal (12×400 + 200)
    EventType.m1500,  # 300m to goal (3×400 + 300)
    EventType.m400,  # Full lap, at finish area
    EventType.m800,  # 2 laps, at finish area
]


# Base distances for hurdles (to determine ordering)
HURDLES_BASE_DISTANCE: dict[EventType, EventType] = {
    EventType.m60_hurdles: EventType.m60,
    EventType.m80_hurdles: EventType.m60,  # 80m hurdles follows 60m block
    EventType.m100_hurdles: EventType.m100,
}

HURDLES_EVENTS: frozenset[EventType] = frozenset(
    {
        EventType.m60_hurdles,
        EventType.m80_hurdles,
        EventType.m100_hurdles,
    }
)


def is_hurdles_event(event_type: EventType) -> bool:
    """Check if an event type is a hurdles event."""
    return event_type in HURDLES_EVENTS


@dataclass(frozen=True)
class HurdleSpec:
    num_hurdles: int
    first_hurdle_m: float
    distance_between_m: float
    height_cm: float


# 60m hurdle specifications by (event_type, category).
# Source: Norwegian Athletics Federation hurdle setup tables.
HURDLE_SPECS: dict[tuple[EventType, Category], HurdleSpec] = {
    # Boys (Gutter) - 60m hurdles
    (EventType.m60_hurdles, Category.g11): HurdleSpec(6, 11, 6.5, 68),
    (EventType.m60_hurdles, Category.g12): HurdleSpec(6, 11, 7, 76.2),
    (EventType.m60_hurdles, Category.g13): HurdleSpec(6, 11.5, 7.5, 76.2),
    (EventType.m60_hurdles, Category.g14): HurdleSpec(5, 12, 8, 84),
    (EventType.m60_hurdles, Category.g15): HurdleSpec(5, 13, 8.5, 84),
    (EventType.m60_hurdles, Category.g16): HurdleSpec(5, 13, 8.5, 91.4),
    (EventType.m60_hurdles, Category.g17): HurdleSpec(5, 13.72, 9.14, 91.4),
    (EventType.m60_hurdles, Category.g18_19): HurdleSpec(5, 13.72, 9.14, 100),
    (EventType.m60_hurdles, Category.ms): HurdleSpec(5, 13.72, 9.14, 106.7),
    # Girls (Jenter) - 60m hurdles
    (EventType.m60_hurdles, Category.j11): HurdleSpec(6, 11, 6.5, 68),
    (EventType.m60_hurdles, Category.j12): HurdleSpec(6, 11, 7, 68),
    (EventType.m60_hurdles, Category.j13): HurdleSpec(6, 11.5, 7.5, 68),
    (EventType.m60_hurdles, Category.j14): HurdleSpec(6, 11.5, 7.5, 76.2),
    (EventType.m60_hurdles, Category.j15): HurdleSpec(5, 12, 8, 76.2),
    (EventType.m60_hurdles, Category.j16): HurdleSpec(5, 12, 8, 76.2),
    (EventType.m60_hurdles, Category.j17): HurdleSpec(5, 13, 8.5, 76.2),
    (EventType.m60_hurdles, Category.j18_19): HurdleSpec(5, 13, 8.5, 84),
    (EventType.m60_hurdles, Category.ks): HurdleSpec(5, 13, 8.5, 84),
}


def get_hurdle_spec(event_type: EventType, category: Category) -> HurdleSpec | None:
    """Get the hurdle specification for an event type and category, or None if not found."""
    return HURDLE_SPECS.get((event_type, category))


def hurdle_lane_capacity(event_type: EventType, categories: list[Category]) -> int:
    """Calculate lane capacity for a hurdle heat with the given categories.

    Categories with different heights need a gutter (empty) lane between
    height zones, reducing capacity from the standard 8 lanes.
    Returns 8 - (num_distinct_heights - 1).
    """
    heights: set[float] = set()
    for cat in categories:
        spec = get_hurdle_spec(event_type, cat)
        if spec is not None:
            heights.add(spec.height_cm)
    if not heights:
        return 8
    return 8 - (len(heights) - 1)


def get_track_event_order(event_type: EventType) -> int:
    """Get the ordering index for a track event type (lower = earlier)."""
    if event_type in TRACK_DISTANCE_ORDER:
        return TRACK_DISTANCE_ORDER.index(event_type)
    return 999  # Non-track events go last


# Venue mappings - events that use the same venue cannot be scheduled simultaneously
EventVenueMapping: dict[EventType, Venue] = {
    # Track events - all use the same track
    EventType.m60: Venue.TRACK,
    EventType.m100: Venue.TRACK,
    EventType.m200: Venue.TRACK,
    EventType.m400: Venue.TRACK,
    EventType.m800: Venue.TRACK,
    EventType.m1500: Venue.TRACK,
    EventType.m5000: Venue.TRACK,
    EventType.m60_hurdles: Venue.TRACK,
    EventType.m80_hurdles: Venue.TRACK,
    EventType.m100_hurdles: Venue.TRACK,
    # Throwing events - use throwing circles/areas
    EventType.sp: Venue.SHOT_PUT_CIRCLE,
    EventType.dt: Venue.THROWING_CIRCLE,
    EventType.ht: Venue.THROWING_CIRCLE,
    EventType.jt: Venue.JAVELIN_AREA,
    EventType.bt: Venue.JAVELIN_AREA,
    # Horizontal jumping events - use jumping pits
    EventType.lj: Venue.JUMPING_PIT,
    EventType.tj: Venue.JUMPING_PIT,
    # Vertical jumping events - each has its own area
    EventType.hj: Venue.HIGH_JUMP_AREA,
    EventType.pv: Venue.HIGH_JUMP_AREA,
}

# Secondary venue configuration: maps event_type to (secondary_venue, eligible_categories).
# The CLI --secondary-venues flag selects which of these are active.
SecondaryVenueConfig: dict[EventType, tuple[Venue, frozenset[Category]]] = {
    EventType.sp: (Venue.SHOT_PUT_CIRCLE_2, YOUNGEST_CATEGORIES),
    EventType.hj: (Venue.HIGH_JUMP_AREA_2, YOUNGEST_CATEGORIES),
}

# Which secondary venues are currently active (set by CLI)
ACTIVE_SECONDARY_VENUES: set[EventType] = set()


def get_venue_for_event(
    event_type: EventType, category: Category | None = None
) -> Venue | None:
    """Get the venue for an event, considering secondary venue assignments.

    If category is provided and a secondary venue is configured for that
    event type and category, returns the secondary venue. Otherwise returns
    the primary venue from EventVenueMapping.
    """
    primary_venue = EventVenueMapping.get(event_type)

    if category is None or event_type not in ACTIVE_SECONDARY_VENUES:
        return primary_venue

    secondary_config = SecondaryVenueConfig.get(event_type)
    if secondary_config is not None:
        secondary_venue, eligible_categories = secondary_config
        if category in eligible_categories:
            return secondary_venue

    return primary_venue


@dataclass
class Event:
    id: str
    event_type: EventType
    age_category: Category
    start_time: str  # ISO 8601 format
    duration_minutes: int
    personnel_required: int
    priority_weight: int  # higher = schedule earlier


@dataclass
class EventGroup:
    id: str
    event_type: EventType
    events: list[Event]

    @property
    def duration_minutes(self) -> int:
        """Calculate duration for the event group.

        For track events: Use maximum duration (events run simultaneously)
        For field events: Sum durations (events run sequentially with shared equipment)
        """
        if not self.events:
            return 0

        # Check if this is a track event
        venue = EventVenueMapping.get(self.event_type)
        if venue == Venue.TRACK:
            # Track events run simultaneously, so use the maximum duration
            return max(event.duration_minutes for event in self.events)
        else:
            # Field events share equipment, so sum the durations
            total = sum(event.duration_minutes for event in self.events)
            # HJ/PV: each individual event includes +5 min setup.
            # Merged groups only pay setup once.
            if self.event_type in (EventType.hj, EventType.pv) and len(self.events) > 1:
                total -= 5 * (len(self.events) - 1)
            return total


@dataclass
class Athlete:
    name: str
    events: list[Event]


EventDuration: dict[EventType, int] = {
    # Track events take time x heats (max 8 per heat)
    EventType.m60: 5,
    EventType.m100: 5,
    EventType.m200: 5,
    EventType.m400: 5,
    EventType.m800: 5,
    EventType.m1500: 10,
    EventType.m5000: 15,
    EventType.m60_hurdles: 5,
    EventType.m80_hurdles: 5,
    EventType.m100_hurdles: 5,
    # Field events take time x number of participants
    # Throw
    EventType.sp: 6,
    EventType.dt: 6,
    EventType.jt: 6,
    EventType.ht: 6,
    EventType.bt: 3,
    # Horizontal jump
    EventType.lj: 6,
    EventType.tj: 6,
    # Vertical jump
    EventType.hj: 6,
    EventType.pv: 12,
}

EventCategoryDurationOverride: dict[tuple[EventType, Category], int] = {
    (EventType.sp, Category.j10): 2,
    (EventType.sp, Category.j11): 2,
    (EventType.sp, Category.j12): 2,
    (EventType.sp, Category.g10): 2,
    (EventType.sp, Category.g11): 2,
    (EventType.sp, Category.g12): 2,
    (EventType.ht, Category.j11): 4,
    (EventType.ht, Category.j12): 4,
    (EventType.ht, Category.g11): 4,
    (EventType.ht, Category.g12): 4,
    (EventType.dt, Category.j11): 4,
    (EventType.dt, Category.j12): 4,
    (EventType.dt, Category.g11): 4,
    (EventType.dt, Category.g12): 4,
    (EventType.lj, Category.j10): 3,
    (EventType.lj, Category.j11): 4,
    (EventType.lj, Category.j12): 4,
    (EventType.lj, Category.g10): 3,
    (EventType.lj, Category.g11): 4,
    (EventType.lj, Category.g12): 4,
    (EventType.hj, Category.j10): 3,
    (EventType.hj, Category.g10): 3,
}

EventCategoryDuration: dict[tuple[EventType, Category], int] = {
    (EventType.m60, Category.j10): 5,
    (EventType.m60, Category.j11): 5,
    (EventType.m60, Category.j12): 5,
    (EventType.m60, Category.j13): 5,
    (EventType.m60, Category.j14): 5,
    (EventType.m60, Category.j15): 5,
    (EventType.m60, Category.j16): 5,
    (EventType.m60, Category.j17): 5,
    (EventType.m60, Category.j18_19): 5,
    (EventType.m60, Category.g10): 5,
    (EventType.m60, Category.g11): 5,
    (EventType.m60, Category.g12): 5,
    (EventType.m60, Category.g13): 5,
    (EventType.m60, Category.g14): 5,
    (EventType.m60, Category.g15): 5,
    (EventType.m60, Category.g16): 5,
    (EventType.m60, Category.g17): 5,
    (EventType.m60, Category.g18_19): 5,
}
