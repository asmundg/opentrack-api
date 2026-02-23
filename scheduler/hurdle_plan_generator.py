"""Hurdle setup plan generator.

Generates an HTML document showing hurdle configurations per lane for each
hurdle heat, for use by the hurdle setup crew.

Supports heats with multiple distance zones (when --mix-hurdle-distances is
used).  Between distance zones, 2 gutter lanes are inserted and styled as
"SONE-SKILLE".  Within a distance zone, different heights still get 1 gutter
lane styled as "LEDIG".
"""

from dataclasses import dataclass

from . import models
from .models import (
    Category,
    EventGroup,
    available_hurdle_lane_list,
    get_hurdle_spec,
    is_hurdles_event,
)
from .types import SchedulingResult


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
    is_distance_gutter: bool = False  # True for 2-lane zone separator
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
    return (
        f'<svg class="marker-icon" viewBox="0 0 20 20">'
        f'<circle cx="10" cy="10" r="8" fill="{color}"/>'
        f'</svg>'
    )


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


def _collect_hurdle_heats(
    result: SchedulingResult,
    start_hour: int,
    start_minute: int,
) -> list[_HurdleHeat]:
    """Walk the schedule and build heat info for each hurdle EventGroup."""
    # Count athletes per individual event id
    athlete_counts: dict[str, int] = {}
    for eg in result.events:
        for ev in eg.events:
            athlete_counts[ev.id] = 0
    for athlete in result.athletes:
        for ev in athlete.events:
            if ev.id in athlete_counts:
                athlete_counts[ev.id] += 1

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
    """Extract distinct distance zones from an EventGroup's categories."""
    # Collect unique (distance, first_hurdle, num_hurdles) combos
    seen: dict[float, _DistanceZone] = {}  # keyed by distance_between_m
    for ev in eg.events:
        spec = get_hurdle_spec(eg.event_type, ev.age_category)
        if spec is None:
            continue
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
    """Assign lanes for a hurdle heat.

    Primary grouping: by distance_between_m (2 gutter lanes between zones).
    Secondary grouping: by height_cm within a distance zone (1 gutter lane).
    """
    # Build (category, distance, height, count) for categories with athletes
    cat_info: list[tuple[Category, float, float, int]] = []
    for ev in eg.events:
        spec = get_hurdle_spec(eg.event_type, ev.age_category)
        if spec is None:
            continue
        count = athlete_counts.get(ev.id, 0)
        if count > 0:
            cat_info.append((ev.age_category, spec.distance_between_m, spec.height_cm, count))

    # Sort by (distance, height, category) for stable grouping
    cat_info.sort(key=lambda x: (x[1], x[2], x[0].value))

    # Group into distance zones, then height zones within each
    # Structure: list of distance zones, each containing list of height zones
    distance_zones: list[list[list[tuple[Category, float, float, int]]]] = []
    current_distance: float | None = None
    current_height: float | None = None
    for item in cat_info:
        _, dist, height, _ = item
        if current_distance is None or dist != current_distance:
            distance_zones.append([])
            current_distance = dist
            current_height = None
        if current_height is None or height != current_height:
            distance_zones[-1].append([])
            current_height = height
        distance_zones[-1][-1].append(item)

    # Count total lanes needed
    num_athletes = sum(count for _, _, _, count in cat_info)
    num_height_gutters = sum(max(0, len(hz) - 1) for hz in distance_zones)
    num_distance_gutters = 2 * max(0, len(distance_zones) - 1)
    total_lanes = num_athletes + num_height_gutters + num_distance_gutters

    # Get available lane numbers (excludes unavailable + age-restricted)
    categories = [cat for cat, _, _, _ in cat_info]
    available = available_hurdle_lane_list(categories)
    offset = (len(available) - total_lanes) // 2

    # Assign lanes using actual available lane numbers
    lanes: list[_LaneInfo] = []
    idx = offset
    for dz_idx, dz_height_zones in enumerate(distance_zones):
        if dz_idx > 0:
            # 2 distance gutter lanes
            for _ in range(2):
                lanes.append(_LaneInfo(
                    lane=available[idx], category=None, height_cm=None,
                    is_distance_gutter=True,
                ))
                idx += 1
        for hz_idx, hz in enumerate(dz_height_zones):
            if hz_idx > 0:
                # 1 height gutter lane
                lanes.append(_LaneInfo(lane=available[idx], category=None, height_cm=None))
                idx += 1
            for cat, dist, height, count in hz:
                for _ in range(count):
                    lanes.append(_LaneInfo(
                        lane=available[idx], category=cat, height_cm=height,
                        distance_between_m=dist,
                    ))
                    idx += 1

    # Insert unavailable lane markers between first and last assigned lane
    if lanes:
        first_lane = lanes[0].lane
        last_lane = lanes[-1].lane
        for blocked in sorted(models.ARENA.unavailable_hurdle_lanes):
            if first_lane < blocked < last_lane:
                # Insert at the right position to keep lanes sorted
                insert_pos = next(
                    i for i, l in enumerate(lanes) if l.lane > blocked
                )
                lanes.insert(insert_pos, _LaneInfo(
                    lane=blocked, category=None, height_cm=None,
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

    # Setup info: one line per zone when multi-zone, single paragraph when single zone
    if len(heat.zones) == 1:
        zone = heat.zones[0]
        marker_html = ""
        if zone.marker:
            label, shape, color = zone.marker
            marker_html = f'&middot; {_marker_icon(shape, color)} <strong>{label}</strong>'
        setup_html = (
            f'        <p class="setup-info">\n'
            f'            {zone.num_hurdles} hekker &middot;\n'
            f'            f&oslash;rste ved {_fmt(zone.first_hurdle_m)} m &middot;\n'
            f'            {_fmt(zone.distance_between_m)} m mellomrom\n'
            f'            {marker_html}\n'
            f'        </p>'
        )
    else:
        lines = []
        for i, zone in enumerate(heat.zones):
            marker_html = ""
            if zone.marker:
                label, shape, color = zone.marker
                marker_html = f'&middot; {_marker_icon(shape, color)} <strong>{label}</strong>'
            lines.append(
                f'            <li>Sone {i+1}: {zone.num_hurdles} hekker &middot; '
                f'f&oslash;rste ved {_fmt(zone.first_hurdle_m)} m &middot; '
                f'{_fmt(zone.distance_between_m)} m mellomrom '
                f'{marker_html}</li>'
            )
        setup_html = (
            f'        <ul class="setup-info">\n'
            + "\n".join(lines)
            + "\n        </ul>"
        )

    rows = ""
    for lane in heat.lanes:
        if lane.is_unavailable:
            rows += (
                f'        <tr class="unavailable">'
                f"<td>{lane.lane}</td>"
                f'<td colspan="2">SPERRET</td>'
                f"</tr>\n"
            )
        elif lane.is_distance_gutter:
            rows += (
                f'        <tr class="distance-gutter">'
                f"<td>{lane.lane}</td>"
                f'<td colspan="2">SONE-SKILLE</td>'
                f"</tr>\n"
            )
        elif lane.category is None:
            rows += (
                f'        <tr class="gutter">'
                f"<td>{lane.lane}</td>"
                f'<td colspan="2">LEDIG</td>'
                f"</tr>\n"
            )
        else:
            assert lane.height_cm is not None
            rows += (
                f"        <tr>"
                f"<td>{lane.lane}</td>"
                f"<td>{lane.category.value}</td>"
                f"<td>{_fmt(lane.height_cm)} cm</td>"
                f"</tr>\n"
            )

    return f"""
    <div class="heat">
        <h2>{header}</h2>
{setup_html}
        <table>
            <thead>
                <tr><th>Bane</th><th>Klasse</th><th>H&oslash;yde</th></tr>
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
"""
