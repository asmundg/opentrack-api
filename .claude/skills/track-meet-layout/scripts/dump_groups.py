#!/usr/bin/env python3
"""Emit a starting schedule_events.csv for a meet (no Z3 solver).

The XLSX holds individual athlete entries; the atom is one (event_type, category)
like "60m J13". A CSV row that lists several categories just means they run at the
same time/venue. Choosing those merges is the agent's job. This script gives a
reasonable STARTING proposal: it merges categories with the repo's default age-tier
logic (mixing boys and girls in a heat, since gender is not a scheduling constraint)
and lays every venue out in parallel from 17:00. You are free to re-merge (split a
row, combine two rows, move categories between rows) as long as from-events still
passes; the merges here are a convenience, not a constraint.

The proposal has no venue conflicts and correct track ordering, but WILL surface the
athlete conflicts that make scheduling hard (one athlete double-booked across two
venues). Resolve those by moving events in time and/or re-merging, re-validating with
from-events. Always validate; this is a seed, not a finished schedule.

The seed only takes --arena and --date (what changes which atoms and venues exist).
The meet's real constraints (--shared, --sticky, --mix-hurdle-distances) are validated
by from-events, not the seed; pass them there. Use the same --arena/--date for both.

    uv run python .claude/skills/track-meet-layout/scripts/dump_groups.py \
        scheduler/goldens/golden-entries-2025-1.xlsx \
        --arena tromsohallen -o schedule_events.csv
"""

import argparse
import csv
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if (_REPO_ROOT / "scheduler").is_dir():
    sys.path.insert(0, str(_REPO_ROOT))

from scheduler import models  # noqa: E402
from scheduler.__main__ import group_events_by_type  # noqa: E402
from scheduler.dtos import EventScheduleRow  # noqa: E402
from scheduler.isonen_parser import parse_isonen_xlsx  # noqa: E402
from scheduler.models import (  # noqa: E402
    EventGroup,
    EventType,
    EventVenueMapping,
    Venue,
    get_category_age_order,
    get_track_event_order,
    get_venue_for_event,
)


def _age_tier(category) -> str:
    """Coarse legal track grouping tier: Rekrutt (<=10), youth (11-17), or senior
    (18-19/Sr/Masters). 11-14 may share a heat with 15-17, so they share one tier;
    only Rekrutt and seniors are forced apart from it."""
    age = get_category_age_order(category)
    if age <= 10:
        return "rekrutt"
    if age <= 17:
        return "youth"
    return "senior"


def _split_track_by_age_tier(groups: list[EventGroup]) -> list[EventGroup]:
    """Split any TRACK group spanning multiple age tiers into one group per tier.

    Mixing genders (the default) can make the repo's grouping merge across an illegal
    track boundary (Rekrutt with older, or 11-14 with seniors). Splitting into
    Rekrutt / youth (11-17) / senior keeps the legal merges (incl. 11-14 + 15-17)
    while removing the illegal cross-tier ones, so the proposal validates.
    """
    out: list[EventGroup] = []
    for g in groups:
        if EventVenueMapping.get(g.event_type) != Venue.TRACK:
            out.append(g)
            continue
        by_tier: dict[str, list] = {}
        for e in g.events:
            by_tier.setdefault(_age_tier(e.age_category), []).append(e)
        if len(by_tier) <= 1:
            out.append(g)
            continue
        for events in by_tier.values():
            cats = "+".join(e.age_category.value for e in events)
            out.append(EventGroup(
                id=f"{g.event_type.value}_{cats}_group",
                event_type=g.event_type,
                events=events,
            ))
    return out


def _youngest(group) -> int:
    return min((get_category_age_order(e.age_category) for e in group.events), default=99)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("xlsx", type=Path, help="Isonen XLSX participant file")
    ap.add_argument("-o", "--output", type=Path, default=Path("schedule_events.csv"))
    ap.add_argument("--arena", default="generic",
                    help="Arena name: sets venues, lane limits and secondary venues. "
                         "Pass the same value to from-events.")
    ap.add_argument("--date", default=None,
                    help="DD.MM.YYYY filter for a multi-day meet. Pass the same value "
                         "to from-events.")
    args = ap.parse_args()

    # The seed only needs what changes which atoms/venues exist: arena and date.
    # All other constraints (--shared, --sticky, --mix-hurdle-distances) are
    # validation concerns the agent passes to from-events, not seed inputs.
    if args.arena not in models.ARENAS:
        ap.error(f"Unknown arena '{args.arena}'. Available: {', '.join(models.ARENAS)}")
    models.ARENA = models.ARENAS[args.arena]
    models.ACTIVE_SECONDARY_VENUES = {
        EventType[name] for name in models.ARENA.default_secondary_venues
    }

    start_str = "17:00"
    events, athletes = parse_isonen_xlsx(str(args.xlsx), filter_date=args.date)
    # Merge by the repo's default age tiers, mixing genders (gender is not a
    # scheduling constraint), then split any track group that crosses the
    # 11-14/15+ boundary so the proposal never contains an age-illegal heat.
    groups = group_events_by_type(events, athletes, mix_genders_track=True)
    groups = _split_track_by_age_tier(groups)

    # Lay each venue out independently from the start time (max parallelism).
    # Within a venue, order events to keep types contiguous (sticky-safe) and put
    # track heats in distance/precedence order. Per-venue serial placement means no
    # venue conflict and correct track ordering; athlete conflicts across venues are
    # left for the agent to resolve with from-events.
    def venue_of(g) -> Venue:
        return get_venue_for_event(g.event_type, g.events[0].age_category) or Venue.TRACK

    def order_key(g) -> tuple:
        if models.EventVenueMapping.get(g.event_type) == Venue.TRACK:
            return (get_track_event_order(g.event_type), _youngest(g), g.event_type.value)
        return (g.event_type.value, _youngest(g))

    by_venue: dict[Venue, list] = defaultdict(list)
    for g in groups:
        by_venue[venue_of(g)].append(g)

    base = datetime.strptime(start_str, "%H:%M")
    placed: list[tuple] = []  # (group, venue, start_dt, end_dt)
    max_end_min = 0
    for venue, vgroups in by_venue.items():
        vgroups.sort(key=order_key)
        slot = 0
        for g in vgroups:
            duration = g.duration_minutes
            start = base + timedelta(minutes=slot * 5)
            end = start + timedelta(minutes=duration)
            placed.append((g, venue, start, end))
            slot += max(1, math.ceil(duration / 5))
            max_end_min = max(max_end_min, slot * 5)

    start_min = base.hour * 60 + base.minute
    if start_min + max_end_min >= 24 * 60:
        ap.error(
            f"Seed overflows midnight (busiest venue needs {max_end_min} min from "
            f"{start_str}). Split the meet by --date, or merge more aggressively."
        )

    placed.sort(key=lambda x: (x[2], x[1].value))
    rows: list[EventScheduleRow] = []
    for g, venue, start, end in placed:
        categories = ",".join(sorted({e.age_category.value for e in g.events}))
        rows.append(EventScheduleRow(
            event_group_id=g.id,
            event_type=g.event_type,
            categories=categories,
            venue=venue,
            start_time=start.time(),
            end_time=end.time(),
            duration_minutes=g.duration_minutes,
        ))

    fieldnames = [
        "event_group_id", "event_type", "categories", "venue",
        "start_time", "end_time", "duration_minutes",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_dict())

    last_end = max(r.end_time for r in rows) if rows else None
    print(f"Wrote {len(rows)} proposed groups to {args.output}")
    print(f"Proposal makespan (venues in parallel): {start_str}-{last_end}.")
    print("Merges here are a starting point — re-merge freely. No venue conflicts yet,")
    print("but expect athlete conflicts to resolve by moving/re-merging events.")
    print("Validate with: uv run opentrack scheduler from-events <xlsx> "
          f"{args.output} -o schedule.html --arena {args.arena} [+ meet constraints]")


if __name__ == "__main__":
    main()
