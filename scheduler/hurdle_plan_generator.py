"""Hurdle setup plan generator.

Generates an HTML document showing hurdle configurations per lane for each
hurdle heat, for use by the hurdle setup crew.
"""

from dataclasses import dataclass

from .models import (
    Category,
    EventGroup,
    HurdleSpec,
    get_hurdle_spec,
    is_hurdles_event,
)
from .types import SchedulingResult


@dataclass
class _LaneInfo:
    lane: int
    category: Category | None  # None = gutter lane
    height_cm: float | None


@dataclass
class _HurdleHeat:
    event_group: EventGroup
    start_time: str
    num_hurdles: int
    first_hurdle_m: float
    distance_between_m: float
    lanes: list[_LaneInfo]
    marker: str | None = None


# Floor markers at Tromsøhallen, keyed by (first_hurdle_m, distance_between_m)
_MARKERS: dict[tuple[float, float], str] = {
    (11.0, 6.5): "Gult kryss",
    (11.0, 7.0): "Rødt kryss",
    (11.5, 7.5): "Blått kryss",
    (12.0, 8.0): "Svart kryss",
    (13.0, 8.5): "Rød ball",
    (13.72, 9.14): "Blå ball",
}


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

            spec = _first_spec(eg)
            if spec is None:
                continue

            lanes = _assign_lanes(eg, athlete_counts)

            heats.append(
                _HurdleHeat(
                    event_group=eg,
                    start_time=time_str,
                    num_hurdles=spec.num_hurdles,
                    first_hurdle_m=spec.first_hurdle_m,
                    distance_between_m=spec.distance_between_m,
                    lanes=lanes,
                )
            )

    return heats


def _first_spec(eg: EventGroup) -> HurdleSpec | None:
    """Return the HurdleSpec for the first category that has one."""
    for ev in eg.events:
        spec = get_hurdle_spec(eg.event_type, ev.age_category)
        if spec is not None:
            return spec
    return None


def _assign_lanes(
    eg: EventGroup,
    athlete_counts: dict[str, int],
) -> list[_LaneInfo]:
    """Assign lanes for a hurdle heat, inserting gutter lanes between height zones."""
    # Build (category, height_cm, athlete_count) for categories with athletes
    cat_info: list[tuple[Category, float, int]] = []
    for ev in eg.events:
        spec = get_hurdle_spec(eg.event_type, ev.age_category)
        if spec is None:
            continue
        count = athlete_counts.get(ev.id, 0)
        if count > 0:
            cat_info.append((ev.age_category, spec.height_cm, count))

    # Sort by height, then category name for stability
    cat_info.sort(key=lambda x: (x[1], x[0].value))

    # Group by height
    height_zones: list[list[tuple[Category, float, int]]] = []
    current_height: float | None = None
    for item in cat_info:
        if current_height is None or item[1] != current_height:
            height_zones.append([])
            current_height = item[1]
        height_zones[-1].append(item)

    # Count total lanes needed (athletes + gutters)
    total_lanes = sum(count for _, _, count in cat_info) + max(0, len(height_zones) - 1)

    # Center across 8 lanes
    max_lanes = 8
    offset = (max_lanes - total_lanes) // 2

    # Assign lanes sequentially, gutter between height zones
    lanes: list[_LaneInfo] = []
    lane_num = 1 + offset
    for zone_idx, zone in enumerate(height_zones):
        if zone_idx > 0:
            lanes.append(_LaneInfo(lane=lane_num, category=None, height_cm=None))
            lane_num += 1
        for cat, height, count in zone:
            for _ in range(count):
                lanes.append(_LaneInfo(lane=lane_num, category=cat, height_cm=height))
                lane_num += 1

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
    <title>Hurdle Setup Plan</title>
    <meta charset="utf-8">
    <style>
{_CSS}
    </style>
</head>
<body>
    <div class="container">
        <h1>Hurdle Setup Plan</h1>
{tables}
    </div>
</body>
</html>"""


def _render_heat(heat: _HurdleHeat) -> str:
    """Render a single hurdle heat as an HTML section."""
    eg = heat.event_group
    categories = " / ".join(ev.age_category.value for ev in eg.events)
    header = f"{eg.event_type.value} &mdash; {categories} &mdash; {heat.start_time}"

    rows = ""
    for lane in heat.lanes:
        if lane.category is None:
            rows += (
                f'        <tr class="gutter">'
                f"<td>{lane.lane}</td>"
                f'<td colspan="2">GUTTER</td>'
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
        <p class="setup-info">
            {heat.num_hurdles} hurdles &middot;
            first at {_fmt(heat.first_hurdle_m)} m &middot;
            {_fmt(heat.distance_between_m)} m apart
        </p>
        <table>
            <thead>
                <tr><th>Lane</th><th>Category</th><th>Height</th></tr>
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
"""
