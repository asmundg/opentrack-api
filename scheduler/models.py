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
    POLE_VAULT_AREA = "pole_vault_area"  # Outdoor PV has its own runway/pit
    JAVELIN_AREA = "javelin_area"


class EventType(Enum):
    m60 = "60m"
    m100 = "100m"
    m150 = "150m"
    m200 = "200m"
    m300 = "300m"
    m400 = "400m"
    m600 = "600m"
    m800 = "800m"
    m1500 = "1500m"
    m3000 = "3000m"
    m5000 = "5000m"
    m60_hurdles = "60m hekk"
    m80_hurdles = "80m hekk"
    m100_hurdles = "100m hekk"
    m200_hurdles = "200m hekk"
    sp = "Kule"
    lj = "Lengde"
    lj_standing = "Lengde uten tilløp"
    tj = "Tresteg"
    hj = "Høyde"
    hj_standing = "Høyde uten tilløp"
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
    # Masters (veteran) brackets, 5-year age bands. Canonical short forms
    # match opentrack_admin.normalize_category() output ("MV30-34" / "KV30-34"
    # etc.). MV = "Menn Veteran" (men masters), KV = "Kvinner Veteran".
    mv30_34 = "MV30-34"
    mv35_39 = "MV35-39"
    mv40_44 = "MV40-44"
    mv45_49 = "MV45-49"
    mv50_54 = "MV50-54"
    mv55_59 = "MV55-59"
    mv60_64 = "MV60-64"
    mv65_69 = "MV65-69"
    mv70_74 = "MV70-74"
    mv75_79 = "MV75-79"
    mv80_84 = "MV80-84"
    mv85_89 = "MV85-89"
    mv90_94 = "MV90-94"
    mv95_99 = "MV95-99"
    kv30_34 = "KV30-34"
    kv35_39 = "KV35-39"
    kv40_44 = "KV40-44"
    kv45_49 = "KV45-49"
    kv50_54 = "KV50-54"
    kv55_59 = "KV55-59"
    kv60_64 = "KV60-64"
    kv65_69 = "KV65-69"
    kv70_74 = "KV70-74"
    kv75_79 = "KV75-79"
    kv80_84 = "KV80-84"
    kv85_89 = "KV85-89"
    kv90_94 = "KV90-94"
    kv95_99 = "KV95-99"
    # Special category for non-athletic events (breaks, etc.) - shown in schedule but ignored for opentrack
    fifa = "FIFA"


# Centralized masters category sets. Defined once so the scheduler, parser,
# HTML generator, and tier configuration can all derive their masters
# membership without each hard-coding the 28 enum members.
MASTERS_MEN: frozenset[Category] = frozenset(
    {
        Category.mv30_34, Category.mv35_39, Category.mv40_44, Category.mv45_49,
        Category.mv50_54, Category.mv55_59, Category.mv60_64, Category.mv65_69,
        Category.mv70_74, Category.mv75_79, Category.mv80_84, Category.mv85_89,
        Category.mv90_94, Category.mv95_99,
    }
)

MASTERS_WOMEN: frozenset[Category] = frozenset(
    {
        Category.kv30_34, Category.kv35_39, Category.kv40_44, Category.kv45_49,
        Category.kv50_54, Category.kv55_59, Category.kv60_64, Category.kv65_69,
        Category.kv70_74, Category.kv75_79, Category.kv80_84, Category.kv85_89,
        Category.kv90_94, Category.kv95_99,
    }
)

MASTERS_CATEGORIES: frozenset[Category] = MASTERS_MEN | MASTERS_WOMEN


# Senior tier: 18-19, regular seniors, and all masters brackets. Used by the
# late-slot push and gender-detection helpers below.
MALE_CATEGORIES: frozenset[Category] = frozenset(
    {
        Category.g10, Category.g11, Category.g12, Category.g13, Category.g14,
        Category.g15, Category.g16, Category.g17, Category.g18_19, Category.ms,
    }
) | MASTERS_MEN

FEMALE_CATEGORIES: frozenset[Category] = frozenset(
    {
        Category.j10, Category.j11, Category.j12, Category.j13, Category.j14,
        Category.j15, Category.j16, Category.j17, Category.j18_19, Category.ks,
    }
) | MASTERS_WOMEN


def is_male_category(category: Category) -> bool:
    """Return True for any boys/men category (including MV* masters)."""
    return category in MALE_CATEGORIES


def is_female_category(category: Category) -> bool:
    """Return True for any girls/women category (including KV* masters)."""
    return category in FEMALE_CATEGORIES


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
    # Masters share the senior tier (run after youth). Per-bracket distinction
    # is preserved through the enum identity, not the ordering value.
    **{cat: 99 for cat in MASTERS_CATEGORIES},
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
    EventType.m150,  # 150m to goal, between 100m straight and 200m bend starts
    EventType.m200,  # 200m to goal
    EventType.m200_hurdles,  # 200m to goal, hurdles
    EventType.m600,  # 600m = 400+200, starts at 200m-to-goal
    EventType.m5000,  # 200m to goal (12×400 + 200)
    EventType.m300,  # 300m to goal
    EventType.m1500,  # 300m to goal (3×400 + 300)
    EventType.m3000,  # 300m to goal (7×400 + 300)
    EventType.m400,  # Full lap, at finish area
    EventType.m800,  # 2 laps, at finish area
]


# Sprint events use the straight track only; round events use the banked oval.
# The re-rig gap (ArenaConfig.sprint_to_round_gap_minutes) applies at the boundary.
SPRINT_EVENTS: frozenset[EventType] = frozenset({
    EventType.m60, EventType.m60_hurdles, EventType.m80_hurdles,
    EventType.m100, EventType.m100_hurdles,
})

ROUND_EVENTS: frozenset[EventType] = frozenset({
    EventType.m150,
    EventType.m200, EventType.m200_hurdles, EventType.m300, EventType.m400,
    EventType.m600, EventType.m800, EventType.m1500, EventType.m3000, EventType.m5000,
})


# Base distances for hurdles (to determine ordering)
HURDLES_BASE_DISTANCE: dict[EventType, EventType] = {
    EventType.m60_hurdles: EventType.m60,
    EventType.m80_hurdles: EventType.m60,  # 80m hurdles follows 60m block
    EventType.m100_hurdles: EventType.m100,
    EventType.m200_hurdles: EventType.m200,
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


# Hurdle specifications by (event_type, category).
# Source: Norwegian Athletics Federation hurdle setup tables.
# Boys 17+ run 110m hurdles (not modelled — no m110_hurdles event type), so they
# are intentionally absent from the 100m hurdle rows below.
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
    # Boys (Gutter) - 80m hurdles (only G14)
    (EventType.m80_hurdles, Category.g14): HurdleSpec(8, 12, 8, 84),
    # Girls (Jenter) - 80m hurdles (J15-16)
    (EventType.m80_hurdles, Category.j15): HurdleSpec(8, 12, 8, 76.2),
    (EventType.m80_hurdles, Category.j16): HurdleSpec(8, 12, 8, 76.2),
    # Boys (Gutter) - 100m hurdles (G15-16; G17+ run 110m hurdles)
    (EventType.m100_hurdles, Category.g15): HurdleSpec(10, 13, 8.5, 84),
    (EventType.m100_hurdles, Category.g16): HurdleSpec(10, 13, 8.5, 91.4),
    # Girls (Jenter) - 100m hurdles (J17+)
    (EventType.m100_hurdles, Category.j17): HurdleSpec(10, 13, 8.5, 76.2),
    (EventType.m100_hurdles, Category.j18_19): HurdleSpec(10, 13, 8.5, 84),
    (EventType.m100_hurdles, Category.ks): HurdleSpec(10, 13, 8.5, 84),
}


def get_hurdle_spec(event_type: EventType, category: Category) -> HurdleSpec | None:
    """Get the hurdle specification for an event type and category, or None if not found."""
    return HURDLE_SPECS.get((event_type, category))


@dataclass(frozen=True)
class ArenaConfig:
    """Venue-specific configuration for lane counts, hurdle markers, etc."""

    name: str
    total_lanes: int
    hurdle_markers: dict[tuple[float, float], tuple[str, str, str]]
    # Age-based lane limits for hurdles: {min_age: max_usable_lanes}
    # E.g., {13: 7} means categories with age >= 13 can use at most 7 lanes.
    hurdle_lane_limits: dict[int, int]
    # Specific lanes to avoid for hurdles (e.g., damaged lane)
    unavailable_hurdle_lanes: frozenset[int] = frozenset()
    # Re-rig gap (minutes) between sprint (straight) and round track events.
    # 0 = no re-rig needed (e.g., permanent oval track).
    sprint_to_round_gap_minutes: int = 0
    # Event types that have a secondary venue available at this arena.
    # Tromsøhallen has two SP circles and two HJ areas; outdoor arenas
    # typically don't.
    default_secondary_venues: frozenset[str] = frozenset()
    # If True, pole vault has its own runway/pit and can run in parallel
    # with high jump. False = PV shares the high jump area.
    pv_separate_from_hj: bool = False


ARENA_GENERIC = ArenaConfig(
    name="generic",
    total_lanes=8,
    hurdle_markers={},
    hurdle_lane_limits={},
)

ARENA_TROMSOHALLEN = ArenaConfig(
    name="tromsohallen",
    total_lanes=8,
    hurdle_markers={
        (11.0, 6.5): ("Gult kryss", "cross", "#DAA520"),
        (11.0, 7.0): ("Rødt kryss", "cross", "#E53935"),
        (11.5, 7.5): ("Blått kryss", "cross", "#1E88E5"),
        (12.0, 8.0): ("Svart kryss", "cross", "#333"),
        (13.0, 8.5): ("Rød ball", "circle", "#E53935"),
        (13.72, 9.14): ("Blå ball", "circle", "#1E88E5"),
    },
    hurdle_lane_limits={13: 7},
    unavailable_hurdle_lanes=frozenset({4}),
    sprint_to_round_gap_minutes=15,
    default_secondary_venues=frozenset({"hj", "sp"}),
    pv_separate_from_hj=False,
)

ARENA_VALHALL = ArenaConfig(
    name="valhall",
    total_lanes=8,
    hurdle_markers={},
    hurdle_lane_limits={},
    pv_separate_from_hj=True,
)

ARENAS: dict[str, ArenaConfig] = {
    "generic": ARENA_GENERIC,
    "tromsohallen": ARENA_TROMSOHALLEN,
    "valhall": ARENA_VALHALL,
}

# Module-level active config, set by CLI (same pattern as ACTIVE_SECONDARY_VENUES)
ARENA: ArenaConfig = ARENA_GENERIC


def available_hurdle_lane_list(categories: list[Category]) -> list[int]:
    """Sorted list of usable lane numbers for a hurdle heat, given ARENA config."""
    max_lanes = ARENA.total_lanes
    for cat in categories:
        age = get_category_age_order(cat)
        for min_age, limit in ARENA.hurdle_lane_limits.items():
            if age >= min_age:
                max_lanes = min(max_lanes, limit)
    return [
        l for l in range(1, max_lanes + 1) if l not in ARENA.unavailable_hurdle_lanes
    ]


def effective_hurdle_lanes(categories: list[Category]) -> int:
    """Max usable lanes for a hurdle heat with these categories, given ARENA config."""
    return len(available_hurdle_lane_list(categories))


def hurdle_lane_capacity(event_type: EventType, categories: list[Category]) -> int:
    """Calculate lane capacity for a hurdle heat with the given categories.

    Each distinct hurdle setup — a unique (distance_between_m, height_cm) pair —
    needs an empty gutter lane between it and the next, whether the difference is in
    distance or height. Capacity is therefore:

        effective_lanes - (num_distinct_setups - 1)

    Categories sharing the exact same setup pack with no gutter between them. When all
    categories share one distance this reduces to "one gutter per distinct height".
    """
    max_lanes = effective_hurdle_lanes(categories)
    setups: set[tuple[float, float]] = set()
    for cat in categories:
        spec = get_hurdle_spec(event_type, cat)
        if spec is not None:
            setups.add((spec.distance_between_m, spec.height_cm))
    if not setups:
        return max_lanes
    return max_lanes - (len(setups) - 1)


def mixed_hurdle_lane_capacity(
    event_type: EventType,
    categories: list[Category],
) -> int:
    """Calculate lane capacity when mixing hurdle categories with different distances.

    Categories are grouped by distance_between_m (distance zones). Between zones,
    2 gutter lanes are needed. Within a zone, heights still need 1 gutter lane each.

    capacity = effective_lanes - 2*(num_distance_zones - 1) - sum(num_heights_in_zone - 1)

    When all categories share the same distance, this reduces to hurdle_lane_capacity.
    """
    max_lanes = effective_hurdle_lanes(categories)
    # Group categories by distance
    by_distance: dict[float, set[float]] = {}
    for cat in categories:
        spec = get_hurdle_spec(event_type, cat)
        if spec is None:
            continue
        by_distance.setdefault(spec.distance_between_m, set()).add(spec.height_cm)

    if not by_distance:
        return max_lanes

    distance_gutters = 2 * (len(by_distance) - 1)
    height_gutters = sum(max(0, len(heights) - 1) for heights in by_distance.values())
    return max_lanes - distance_gutters - height_gutters


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
    EventType.m150: Venue.TRACK,
    EventType.m200: Venue.TRACK,
    EventType.m300: Venue.TRACK,
    EventType.m400: Venue.TRACK,
    EventType.m600: Venue.TRACK,
    EventType.m800: Venue.TRACK,
    EventType.m1500: Venue.TRACK,
    EventType.m3000: Venue.TRACK,
    EventType.m5000: Venue.TRACK,
    EventType.m60_hurdles: Venue.TRACK,
    EventType.m80_hurdles: Venue.TRACK,
    EventType.m100_hurdles: Venue.TRACK,
    EventType.m200_hurdles: Venue.TRACK,
    # Throwing events - use throwing circles/areas
    EventType.sp: Venue.SHOT_PUT_CIRCLE,
    EventType.dt: Venue.THROWING_CIRCLE,
    EventType.ht: Venue.THROWING_CIRCLE,
    EventType.jt: Venue.JAVELIN_AREA,
    EventType.bt: Venue.JAVELIN_AREA,
    # Horizontal jumping events - use jumping pits
    EventType.lj: Venue.JUMPING_PIT,
    EventType.lj_standing: Venue.JUMPING_PIT,
    EventType.tj: Venue.JUMPING_PIT,
    # Vertical jumping events - each has its own area
    EventType.hj: Venue.HIGH_JUMP_AREA,
    EventType.hj_standing: Venue.HIGH_JUMP_AREA,
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

# Groups of event types that share a venue/officials and cannot run in parallel.
# Set by CLI via --shared. Each group is a frozenset of EventType. The scheduler
# folds every member onto a synthetic shared key in ADDITION to its natural
# venue, so shared events still conflict at their physical venue too. Display
# and grouping code keep using the natural venue.
SHARED_VENUE_GROUPS: list[frozenset[EventType]] = []

# When True, the scheduler forbids interleaving different event types at the
# same scheduling venue key (e.g., DT-HT-DT at the throwing circle is rejected;
# events of one type must run as a contiguous block). Track is never sticky --
# it has its own precedence rules. Toggle via CLI --sticky/--no-sticky.
STICKY_VENUES: bool = True


def get_venue_for_event(
    event_type: EventType, category: Category | None = None
) -> Venue | None:
    """Get the venue for an event, considering secondary venue assignments
    and arena-specific overrides.

    If the active arena marks PV as separate from HJ, pole vault returns
    POLE_VAULT_AREA so it can run in parallel with high jump.
    """
    if event_type == EventType.pv and ARENA.pv_separate_from_hj:
        return Venue.POLE_VAULT_AREA

    primary_venue = EventVenueMapping.get(event_type)

    if category is None or event_type not in ACTIVE_SECONDARY_VENUES:
        return primary_venue

    secondary_config = SecondaryVenueConfig.get(event_type)
    if secondary_config is not None:
        secondary_venue, eligible_categories = secondary_config
        if category in eligible_categories:
            return secondary_venue

    return primary_venue


def get_scheduling_venue_keys(
    event_type: EventType, venue: Venue | None
) -> set[str]:
    """Return the conflict-bucket keys that this event participates in.

    Every event lives at its natural venue (e.g., jumping_pit). Events in a
    declared shared-venue group ALSO live at a synthetic shared key
    (e.g., "shared:hj,lj"). The scheduler treats each key as an independent
    "at most one active per slot" bucket, so a Lengde event with --shared lj,hj
    still conflicts with a Tresteg event at the jumping pit AND with a Høyde
    event at the shared-officials bucket.

    Returns an empty set for events with no venue (which never conflict).
    """
    keys: set[str] = set()
    if venue is not None:
        keys.add(venue.value)
    for group in SHARED_VENUE_GROUPS:
        if event_type in group:
            keys.add("shared:" + ",".join(sorted(et.name for et in group)))
    return keys


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
    EventType.m150: 5,
    EventType.m200: 5,
    EventType.m300: 5,
    EventType.m400: 5,
    EventType.m600: 5,
    EventType.m800: 5,
    EventType.m1500: 10,
    EventType.m3000: 15,
    EventType.m5000: 15,
    EventType.m60_hurdles: 5,
    EventType.m80_hurdles: 5,
    EventType.m100_hurdles: 5,
    EventType.m200_hurdles: 5,
    # Field events take time x number of participants
    # Throw
    EventType.sp: 6,
    EventType.dt: 6,
    EventType.jt: 6,
    EventType.ht: 6,
    EventType.bt: 3,
    # Horizontal jump
    EventType.lj: 6,
    EventType.lj_standing: 4,
    EventType.tj: 6,
    # Vertical jump
    EventType.hj: 6,
    EventType.hj_standing: 4,
    EventType.pv: 12,
}

EventCategoryDurationOverride: dict[tuple[EventType, Category], int] = {
    (EventType.sp, Category.j10): 2,
    (EventType.sp, Category.j11): 4,
    (EventType.sp, Category.j12): 4,
    (EventType.sp, Category.g10): 2,
    (EventType.sp, Category.g11): 4,
    (EventType.sp, Category.g12): 4,
    (EventType.ht, Category.j11): 4,
    (EventType.ht, Category.j12): 4,
    (EventType.ht, Category.g11): 4,
    (EventType.ht, Category.g12): 4,
    (EventType.dt, Category.j11): 4,
    (EventType.dt, Category.j12): 4,
    (EventType.dt, Category.g11): 4,
    (EventType.dt, Category.g12): 4,
    (EventType.jt, Category.j11): 4,
    (EventType.jt, Category.j12): 4,
    (EventType.jt, Category.g11): 4,
    (EventType.jt, Category.g12): 4,
    (EventType.lj, Category.j10): 3,
    (EventType.lj, Category.j11): 4,
    (EventType.lj, Category.j12): 4,
    (EventType.lj, Category.g10): 3,
    (EventType.lj, Category.g11): 4,
    (EventType.lj, Category.g12): 4,
    (EventType.hj, Category.j10): 4,
    (EventType.hj, Category.g10): 4,
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
