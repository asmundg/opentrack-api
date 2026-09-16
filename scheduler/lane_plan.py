"""Track lane assignment, and the hurdle setup plan the crew rigs from.

Lanes in a track heat are grouped into *bands* of athletes with identical lane
requirements, and each band is separated from the next by one empty gutter lane.
A band is a unique combination of:

* hurdle spacing — different spacing needs its own zone ("SONE-SKILLE")
* hurdle height — a height change needs an empty lane to work in ("LEDIG")
* start type — blocks vs standing (see `models.uses_starting_blocks`)

Lanes within a band are interchangeable, so the start list seeds them by
performance; the bands and their gutters are what this module fixes.
"""

from dataclasses import dataclass

from shared.lanes import is_staggered, lane_preference

from . import models
from .models import (
    Category,
    EventGroup,
    TRACK_DISTANCE_ORDER,
    available_hurdle_lane_list,
    get_category_age_order,
    get_hurdle_spec,
    is_hurdles_event,
    uses_starting_blocks,
)
from .types import SchedulingResult


@dataclass(frozen=True)
class _Band:
    """The lane requirements shared by one contiguous run of lanes."""

    distance_between_m: float | None
    height_cm: float | None
    blocks: bool


def _band_order(band: _Band) -> tuple[float, float, bool]:
    """Sort key placing standing starters before block starters."""
    return (
        band.distance_between_m if band.distance_between_m is not None else -1.0,
        band.height_cm if band.height_cm is not None else -1.0,
        band.blocks,
    )


@dataclass
class _DistanceZone:
    """One group of lanes sharing the same hurdle spacing."""
    distance_between_m: float
    first_hurdle_m: float
    num_hurdles: int
    marker: tuple[str, str, str] | None  # (label, shape, color)


@dataclass
class _LaneInfo:
    lane: int
    category: Category | None  # None = gutter lane
    height_cm: float | None
    distance_between_m: float | None = None
    is_distance_gutter: bool = False  # True for a distance-zone separator lane
    is_unavailable: bool = False  # True for blocked/damaged lanes


@dataclass
class _HurdleHeat:
    event_group: EventGroup
    start_time: str
    zones: list[_DistanceZone]
    lanes: list[_LaneInfo]



def _marker_icon(shape: str, color: str) -> str:
    """Return an inline SVG icon for a floor marker."""
    if shape == "cross":
        return (
            f'<svg class="marker-icon" viewBox="0 0 20 20">'
            f'<line x1="10" y1="3" x2="10" y2="17" stroke="{color}" stroke-width="4" stroke-linecap="round"/>'
            f'<line x1="3" y1="10" x2="17" y2="10" stroke="{color}" stroke-width="4" stroke-linecap="round"/>'
            f'</svg>'
        )
    if shape == "triangle":
        return (
            f'<svg class="marker-icon" viewBox="0 0 20 20">'
            f'<polygon points="10,2 18,17 2,17" fill="{color}"/>'
            f'</svg>'
        )
    if shape == "square":
        return (
            f'<svg class="marker-icon" viewBox="0 0 20 20">'
            f'<rect x="3" y="3" width="14" height="14" fill="{color}"/>'
            f'</svg>'
        )
    if shape == "line":
        return (
            f'<svg class="marker-icon" viewBox="0 0 20 20">'
            f'<line x1="3" y1="10" x2="17" y2="10" stroke="{color}" stroke-width="4" stroke-linecap="round"/>'
            f'</svg>'
        )
    return (
        f'<svg class="marker-icon" viewBox="0 0 20 20">'
        f'<circle cx="10" cy="10" r="8" fill="{color}"/>'
        f'</svg>'
    )


def _marker_cell(marker: tuple[str, str, str] | None) -> str:
    """Render a lane's floor-marker cell (icon + label), or a dash if none."""
    if not marker:
        return '<span class="no-marker">&ndash;</span>'
    label, shape, color = marker
    return f'{_marker_icon(shape, color)} <strong>{label}</strong>'


def generate_hurdle_plan_html(
    result: SchedulingResult,
    start_hour: int,
    start_minute: int,
) -> str | None:
    """Generate an HTML hurdle setup plan from a scheduling result.

    Returns HTML string, or None if no hurdle events in the schedule.
    """
    heats = _collect_hurdle_heats(result, start_hour, start_minute)
    if not heats:
        return None
    return _render_html(heats)


def track_lane_assignments(
    result: SchedulingResult,
    start_hour: int,
    start_minute: int,
) -> list[tuple[str, str, int]]:
    """Lanes to impose on the start lists, as (event_type, categories, lane).

    One row per occupied lane, with `categories` naming the whole band that lane
    belongs to, so the start list can seed a band's lanes by performance while
    keeping the bands apart. Gutter and blocked lanes are simply absent.

    Emitted for hurdle heats (each lane carries specific equipment) and for any
    other track heat split into more than one band; a single-band flat heat has
    no lane requirements worth imposing, so the normal seeded draw is left alone.
    """
    counts = _athlete_counts(result)
    rows: list[tuple[str, str, int]] = []
    for eg in _track_groups(result):
        lanes = _assign_lanes(eg, counts)
        bands = _bands(eg, counts)
        if not is_hurdles_event(eg.event_type) and len(set(bands.values())) < 2:
            continue
        for lane in lanes:
            if lane.category is None:
                continue
            rows.append((eg.event_type.value, bands[lane.category], lane.lane))
    return rows


def _bands(eg: EventGroup, counts: dict[str, int]) -> dict[Category, str]:
    """Map each category with athletes to its band's comma-joined categories."""
    members: dict[_Band, list[Category]] = {}
    for ev in eg.events:
        if counts.get(ev.id, 0) <= 0:
            continue
        spec = get_hurdle_spec(eg.event_type, ev.age_category)
        if is_hurdles_event(eg.event_type) and spec is None:
            continue
        band = _Band(
            distance_between_m=spec.distance_between_m if spec else None,
            height_cm=spec.height_cm if spec else None,
            blocks=uses_starting_blocks(eg.event_type, ev.age_category),
        )
        members.setdefault(band, []).append(ev.age_category)
    return {
        category: ",".join(sorted(c.value for c in categories))
        for categories in members.values()
        for category in categories
    }


def _track_groups(result: SchedulingResult):
    """Every track EventGroup in the schedule, in running order."""
    for _, entries in sorted(result.schedule.items()):
        for entry in entries:
            if entry["is_start"] and entry["event"].event_type in TRACK_DISTANCE_ORDER:
                yield entry["event"]


def _athlete_counts(result: SchedulingResult) -> dict[str, int]:
    """Number of athletes entered in each individual event."""
    counts = {ev.id: 0 for eg in result.events for ev in eg.events}
    for athlete in result.athletes:
        for ev in athlete.events:
            if ev.id in counts:
                counts[ev.id] += 1
    return counts


def _collect_hurdle_heats(
    result: SchedulingResult,
    start_hour: int,
    start_minute: int,
) -> list[_HurdleHeat]:
    """Walk the schedule and build heat info for each hurdle EventGroup."""
    athlete_counts = _athlete_counts(result)

    heats: list[_HurdleHeat] = []

    for slot, entries in sorted(result.schedule.items()):
        for entry in entries:
            if not entry["is_start"]:
                continue
            eg: EventGroup = entry["event"]
            if not is_hurdles_event(eg.event_type):
                continue

            time_min = start_hour * 60 + start_minute + slot * result.slot_duration_minutes
            time_str = f"{time_min // 60}:{time_min % 60:02d}"

            zones = _extract_zones(eg)
            if not zones:
                continue

            lanes = _assign_lanes(eg, athlete_counts)

            heats.append(
                _HurdleHeat(
                    event_group=eg,
                    start_time=time_str,
                    zones=zones,
                    lanes=lanes,
                )
            )

    return heats


def _extract_zones(eg: EventGroup) -> list[_DistanceZone]:
    """Extract distinct distance zones from an EventGroup's categories.

    Raises if a category has no hurdle spec: the crew cannot rig a heat we have
    no geometry for, and silently dropping it would print a plan missing a race.
    """
    # Collect unique (distance, first_hurdle, num_hurdles) combos
    seen: dict[float, _DistanceZone] = {}  # keyed by distance_between_m
    for ev in eg.events:
        spec = get_hurdle_spec(eg.event_type, ev.age_category)
        if spec is None:
            raise ValueError(
                f"No hurdle spec for {eg.event_type.value} "
                f"{ev.age_category.value}: add it to HURDLE_SPECS in "
                "scheduler/models.py so the setup crew gets a card for this heat."
            )
        if spec.distance_between_m not in seen:
            marker = models.ARENA.hurdle_markers.get((spec.first_hurdle_m, spec.distance_between_m))
            seen[spec.distance_between_m] = _DistanceZone(
                distance_between_m=spec.distance_between_m,
                first_hurdle_m=spec.first_hurdle_m,
                num_hurdles=spec.num_hurdles,
                marker=marker,
            )
    return [seen[d] for d in sorted(seen)]


def _assign_lanes(
    eg: EventGroup,
    athlete_counts: dict[str, int],
) -> list[_LaneInfo]:
    """Assign lanes for a track heat, one gutter lane between adjacent bands.

    When blocked lanes exist, tries to position the layout so blocked lanes
    coincide with gutter positions (saving a usable lane). Straight races sit
    in the middle of the track. Staggered races take the lanes the seeded draw
    prefers, which keeps athletes off the tight bends.
    """
    hurdles = is_hurdles_event(eg.event_type)
    staggered = is_staggered(eg.event_type.value)
    preference = lane_preference(models.ARENA.total_lanes, staggered=True)

    # Build (category, band, count) for categories with athletes
    cat_info: list[tuple[Category, _Band, int]] = []
    for ev in eg.events:
        spec = get_hurdle_spec(eg.event_type, ev.age_category)
        if hurdles and spec is None:
            continue
        count = athlete_counts.get(ev.id, 0)
        if count <= 0:
            continue
        cat_info.append((
            ev.age_category,
            _Band(
                distance_between_m=spec.distance_between_m if spec else None,
                height_cm=spec.height_cm if spec else None,
                blocks=uses_starting_blocks(eg.event_type, ev.age_category),
            ),
            count,
        ))

    cat_info.sort(key=lambda x: (_band_order(x[1]), x[0].value))

    # Build logical layout: flat sequence of slots to place on physical lanes
    _ATHLETE = "athlete"
    _HEIGHT_GUTTER = "height_gutter"
    _DISTANCE_GUTTER = "distance_gutter"

    layout: list[tuple[str, Category | None, float | None, float | None]] = []
    previous: _Band | None = None
    for cat, band, count in cat_info:
        if previous is not None and band != previous:
            # Only a spacing change makes it a distance zone; a height or start
            # change just needs the lane left free.
            layout.append((
                _DISTANCE_GUTTER
                if band.distance_between_m != previous.distance_between_m
                else _HEIGHT_GUTTER,
                None, None, None,
            ))
        for _ in range(count):
            layout.append((_ATHLETE, cat, band.height_cm, band.distance_between_m))
        previous = band

    total_slots = len(layout)
    gutter_indices = {i for i, (kind, *_) in enumerate(layout) if kind != _ATHLETE}
    athlete_indices = [i for i in range(total_slots) if i not in gutter_indices]
    categories = [cat for cat, _, _ in cat_info]

    # Compute max lane number (age-limited, but including blocked lanes)
    max_lane = models.ARENA.total_lanes
    if hurdles:
        for cat in categories:
            age = get_category_age_order(cat)
            for min_age, limit in models.ARENA.hurdle_lane_limits.items():
                if age >= min_age:
                    max_lane = min(max_lane, limit)

    blocked = (
        {l for l in models.ARENA.unavailable_hurdle_lanes if 1 <= l <= max_lane}
        if hurdles
        else set()
    )

    # Try contiguous placements: pick one where blocked lanes align with gutters
    best_start: int | None = None
    best_score: tuple[int, float] | None = None

    if blocked and gutter_indices:
        for start in range(1, max_lane - total_slots + 2):
            valid = True
            gutter_matches = 0
            for i in range(total_slots):
                lane = start + i
                if lane in blocked:
                    if i in gutter_indices:
                        gutter_matches += 1
                    else:
                        valid = False
                        break
            if not valid:
                continue
            if staggered:
                placement = -sum(preference.index(start + i) for i in athlete_indices)
            else:
                center = (1 + max_lane) / 2
                placement = -abs((start + (total_slots - 1) / 2) - center)
            score = (gutter_matches, placement)
            if best_score is None or score > best_score:
                best_score = score
                best_start = start

    if best_start is not None and best_score is not None and best_score[0] > 0:
        # Contiguous placement with blocked lanes aligned to gutters
        lanes: list[_LaneInfo] = []
        for i, (kind, cat, height, dist) in enumerate(layout):
            lane_num = best_start + i
            is_blocked = lane_num in blocked
            if kind == _ATHLETE:
                lanes.append(_LaneInfo(
                    lane=lane_num, category=cat, height_cm=height,
                    distance_between_m=dist,
                ))
            elif kind == _DISTANCE_GUTTER:
                lanes.append(_LaneInfo(
                    lane=lane_num, category=None, height_cm=None,
                    is_distance_gutter=True, is_unavailable=is_blocked,
                ))
            else:  # height gutter
                lanes.append(_LaneInfo(
                    lane=lane_num, category=None, height_cm=None,
                    is_unavailable=is_blocked,
                ))
        return lanes

    # Fallback: skip blocked lanes, place within the available lanes
    available = (
        available_hurdle_lane_list(categories)
        if hurdles
        else list(range(1, models.ARENA.total_lanes + 1))
    )
    if staggered:
        offset = min(
            range(len(available) - total_slots + 1),
            key=lambda o: sum(preference.index(available[o + i]) for i in athlete_indices),
        )
    else:
        offset = (len(available) - total_slots) // 2

    lanes = []
    for i, (kind, cat, height, dist) in enumerate(layout):
        lane_num = available[offset + i]
        if kind == _ATHLETE:
            lanes.append(_LaneInfo(
                lane=lane_num, category=cat, height_cm=height,
                distance_between_m=dist,
            ))
        elif kind == _DISTANCE_GUTTER:
            lanes.append(_LaneInfo(
                lane=lane_num, category=None, height_cm=None,
                is_distance_gutter=True,
            ))
        else:  # height gutter
            lanes.append(_LaneInfo(lane=lane_num, category=None, height_cm=None))

    # Insert blocked lane markers between first and last assigned lane
    if lanes:
        first_lane = lanes[0].lane
        last_lane = lanes[-1].lane
        assigned = {l.lane for l in lanes}
        for b in sorted(blocked):
            if first_lane < b < last_lane and b not in assigned:
                insert_pos = next(i for i, l in enumerate(lanes) if l.lane > b)
                lanes.insert(insert_pos, _LaneInfo(
                    lane=b, category=None, height_cm=None,
                    is_unavailable=True,
                ))

    return lanes


def _fmt(v: float) -> str:
    """Format a float, stripping unnecessary trailing zeros."""
    return f"{v:g}"


def _render_html(heats: list[_HurdleHeat]) -> str:
    """Render all hurdle heats as an HTML document."""
    tables = "\n".join(_render_heat(h) for h in heats)
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Hekkeplan</title>
    <meta charset="utf-8">
    <style>
{_CSS}
    </style>
</head>
<body>
    <div class="container">
        <h1>Hekkeplan</h1>
{tables}
    </div>
</body>
</html>"""


def _render_heat(heat: _HurdleHeat) -> str:
    """Render a single hurdle heat as an HTML section."""
    eg = heat.event_group
    categories = " / ".join(ev.age_category.value for ev in eg.events)
    header = f"{eg.event_type.value} &mdash; {categories} &mdash; {heat.start_time}"

    # Setup info: one line per zone when multi-zone, single paragraph when single zone.
    # The floor marker now lives per lane (Merke column), so it's not repeated here.
    if len(heat.zones) == 1:
        zone = heat.zones[0]
        setup_html = (
            f'        <p class="setup-info">\n'
            f'            {zone.num_hurdles} hekker &middot;\n'
            f'            f&oslash;rste ved {_fmt(zone.first_hurdle_m)} m &middot;\n'
            f'            {_fmt(zone.distance_between_m)} m mellomrom\n'
            f'        </p>'
        )
    else:
        lines = []
        for i, zone in enumerate(heat.zones):
            lines.append(
                f'            <li>Sone {i+1}: {zone.num_hurdles} hekker &middot; '
                f'f&oslash;rste ved {_fmt(zone.first_hurdle_m)} m &middot; '
                f'{_fmt(zone.distance_between_m)} m mellomrom</li>'
            )
        setup_html = (
            '        <ul class="setup-info">\n'
            + "\n".join(lines)
            + "\n        </ul>"
        )

    # Marker per distance zone, looked up by each lane's spacing.
    marker_by_dist = {z.distance_between_m: z.marker for z in heat.zones}

    rows = ""
    for lane in heat.lanes:
        if lane.is_distance_gutter:
            label = "SONE-SKILLE (SPERRET)" if lane.is_unavailable else "SONE-SKILLE"
            rows += (
                f'        <tr class="distance-gutter">'
                f"<td>{lane.lane}</td>"
                f'<td colspan="3">{label}</td>'
                f"</tr>\n"
            )
        elif lane.is_unavailable:
            rows += (
                f'        <tr class="unavailable">'
                f"<td>{lane.lane}</td>"
                f'<td colspan="3">SPERRET</td>'
                f"</tr>\n"
            )
        elif lane.category is None:
            rows += (
                f'        <tr class="gutter">'
                f"<td>{lane.lane}</td>"
                f'<td colspan="3">LEDIG</td>'
                f"</tr>\n"
            )
        else:
            assert lane.height_cm is not None
            marker = marker_by_dist.get(lane.distance_between_m)
            rows += (
                f"        <tr>"
                f"<td>{lane.lane}</td>"
                f"<td>{lane.category.value}</td>"
                f"<td>{_fmt(lane.height_cm)} cm</td>"
                f"<td>{_marker_cell(marker)}</td>"
                f"</tr>\n"
            )

    return f"""
    <div class="heat">
        <h2>{header}</h2>
{setup_html}
        <table>
            <thead>
                <tr><th>Bane</th><th>Klasse</th><th>H&oslash;yde</th><th>Merke</th></tr>
            </thead>
            <tbody>
{rows}
            </tbody>
        </table>
    </div>"""


_CSS = """\
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 800px; margin: 0 auto;
            background: white; padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            text-align: center; color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }
        .heat { margin-bottom: 30px; }
        .heat h2 {
            margin-bottom: 4px; font-size: 18px; color: #333;
        }
        .setup-info {
            margin-top: 0; color: #555; font-style: italic;
        }
        ul.setup-info {
            padding-left: 20px;
        }
        table {
            border-collapse: collapse; width: 100%;
        }
        th, td {
            border: 1px solid #ddd; padding: 8px; text-align: left;
        }
        th {
            background-color: #4CAF50; color: white;
        }
        tr.gutter td {
            background-color: #f0f0f0; color: #999;
            font-style: italic; text-align: center;
        }
        tr.distance-gutter td {
            background-color: #ffcccc; color: #c62828;
            font-weight: bold; font-style: italic; text-align: center;
        }
        tr.unavailable td {
            background-color: #fff3e0; color: #e65100;
            font-weight: bold; font-style: italic; text-align: center;
        }
        .marker-icon {
            width: 18px; height: 18px;
            vertical-align: middle;
            margin-right: 2px;
        }
        .no-marker { color: #bbb; }
"""
