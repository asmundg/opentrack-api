#!/usr/bin/env python3
"""Detect mistakes and report compactness for a schedule_events.csv.

This is a conflict/quality detector, not a layout designer. Deciding merges and
placement is the agent's job (see the skill's heuristics); this tool only tells you
what is wrong and how tight the result is. `from-events` is the authoritative gate but
stops at the FIRST violation; this surfaces ALL problems at once and adds compactness
metrics:
  - makespan, per-venue utilization, idle gaps (compaction opportunities), parallelism
  - cheap local pre-checks: 5-min slot alignment, same-venue overlaps
  - track-heat spacing (>=5 min on a start-position change or between hurdle heats)
  - field reconfig spacing (>=5 min when the event type changes at a venue/shared
    bucket; pass the same --shared groups you give from-events to catch cross-venue
    transitions like Spyd -> Slegge)
  - with --xlsx: EVERY athlete double-booking and age-merge violation at once

It does NOT replace `from-events`. Shared-venue (--shared), stickiness and track
ordering are only enforced by `from-events`.

    uv run python .claude/skills/track-meet-layout/scripts/layout_report.py schedule_events.csv
    uv run python .claude/skills/track-meet-layout/scripts/layout_report.py schedule_events.csv \
        --xlsx participants.xlsx --arena tromsohallen --date 30.05.2026
"""

import argparse
import csv
import math
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _mins(t: str) -> int:
    dt = datetime.strptime(t.strip(), "%H:%M")
    return dt.hour * 60 + dt.minute


def _resolve_shared(shared: list[str]) -> list[set[str]]:
    """Map repeated --shared code lists (e.g. 'jt,dt,ht') to sets of display labels.

    Mirrors from-events: each event type runs at its own venue but a group shares
    personnel, so the whole group is one serial stream. Labels (Spyd, Slegge, ...)
    are what the CSV's event_type column holds.
    """
    if not shared:
        return []
    if (_REPO_ROOT / "scheduler").is_dir():
        sys.path.insert(0, str(_REPO_ROOT))
    from scheduler.models import EventType

    groups: list[set[str]] = []
    for raw in shared:
        labels: set[str] = set()
        for name in (n.strip() for n in raw.split(",") if n.strip()):
            try:
                labels.add(EventType[name].value)
            except KeyError:
                valid = ", ".join(e.name for e in EventType)
                sys.exit(f"Unknown event type '{name}' in --shared. Valid: {valid}")
        if len(labels) >= 2:
            groups.append(labels)
    return groups


def _xlsx_checks(csv_path: Path, args) -> tuple[list[str], list[str]]:
    """Return (athlete_conflicts, age_violations) for the agent's CSV layout.

    Athlete membership is taken from the CSV's own merges (each row's categories),
    matching exactly what from-events validates. Reuses the validator's age rules so
    this batch view and the authoritative gate never drift.
    """
    if (_REPO_ROOT / "scheduler").is_dir():
        sys.path.insert(0, str(_REPO_ROOT))
    from scheduler import models
    from scheduler.isonen_parser import parse_isonen_xlsx
    from scheduler.event_csv import import_event_overview_csv
    from scheduler.constraint_validator import age_merge_errors, _atom_counts
    from scheduler.models import Category, EventType, get_category_age_order

    if args.arena not in models.ARENAS:
        sys.exit(f"Unknown arena '{args.arena}'")
    models.ARENA = models.ARENAS[args.arena]
    models.ACTIVE_SECONDARY_VENUES = {
        EventType[n] for n in models.ARENA.default_secondary_venues
    }
    events, athletes = parse_isonen_xlsx(str(args.xlsx), filter_date=args.date)
    rows = import_event_overview_csv(csv_path)

    # atom (event_type, category) -> (group_id, start, end), from the CSV merges
    atom_to_row: dict[tuple[EventType, Category], tuple[str, int, int]] = {}
    for r in rows:
        span = (r.event_group_id, _mins(r.start_time.strftime("%H:%M")),
                _mins(r.end_time.strftime("%H:%M")))
        for raw in r.categories.split(","):
            name = raw.strip()
            if not name:
                continue
            try:
                atom_to_row[(r.event_type, Category(name))] = span
            except ValueError:
                continue

    conflicts: list[str] = []
    recovery: list[str] = []
    for ath in athletes:
        age_order = max(
            (get_category_age_order(e.age_category) for e in ath.events), default=0
        )
        seen: set[str] = set()
        intervals = []
        for e in ath.events:
            span = atom_to_row.get((e.event_type, e.age_category))
            if span and span[0] not in seen:
                seen.add(span[0])
                intervals.append((span[1], span[2], span[0]))
        intervals.sort()
        for a, b in zip(intervals, intervals[1:]):
            if b[0] < a[1]:
                conflicts.append(
                    f"{ath.name}: {a[2]} ({a[0]//60:02d}:{a[0]%60:02d}-"
                    f"{a[1]//60:02d}:{a[1]%60:02d}) overlaps {b[2]} "
                    f"({b[0]//60:02d}:{b[0]%60:02d}-{b[1]//60:02d}:{b[1]%60:02d})")
                continue
            gap = b[0] - a[1]
            if age_order >= 13 and gap < 10:
                recovery.append(
                    f"FAIL {ath.name}: only {gap}m between {a[2]} and {b[2]} "
                    f"(13+ need >=10m)")
            elif age_order >= 15 and gap < 15:
                recovery.append(
                    f"warn {ath.name}: only {gap}m between {a[2]} and {b[2]} "
                    f"(15+ prefer >=15m)")

    counts = _atom_counts(athletes)
    age = age_merge_errors(rows, counts)
    return conflicts, age, recovery


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--gap", type=int, default=5,
                    help="Report idle gaps >= this many minutes (default 5)")
    ap.add_argument("--xlsx", type=Path, default=None,
                    help="Participant XLSX; enables full athlete-conflict listing")
    ap.add_argument("--arena", default="generic")
    ap.add_argument("--date", default=None)
    ap.add_argument("--shared", action="append", default=[],
                    help="Shared personnel group as event-type codes, e.g. "
                         "--shared jt,dt,bt,ht,sp (repeatable). Mirror from-events "
                         "so cross-venue reconfig gaps are checked.")
    args = ap.parse_args()

    rows = list(csv.DictReader(args.csv.open(encoding="utf-8")))
    if not rows:
        ap.error("empty CSV")

    events = []
    for r in rows:
        s, e = _mins(r["start_time"]), _mins(r["end_time"])
        events.append({
            "id": r["event_group_id"], "venue": r["venue"], "type": r["event_type"],
            "start": s, "end": e, "dur": e - s,
        })

    base = min(ev["start"] for ev in events)
    end = max(ev["end"] for ev in events)
    makespan = end - base

    # --- cheap pre-checks ---
    warnings: list[str] = []
    for ev in events:
        if (ev["start"] - base) % 5 != 0:
            warnings.append(f"{ev['id']}: start not on 5-min boundary "
                            f"(crashes from-events at build)")

    by_venue: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        by_venue[ev["venue"]].append(ev)
    for venue, evs in by_venue.items():
        evs.sort(key=lambda x: x["start"])
        for a, b in zip(evs, evs[1:]):
            if b["start"] < a["end"]:
                warnings.append(f"venue {venue}: {a['id']} ({a['start']-base}-"
                                f"{a['end']-base}m) overlaps {b['id']} "
                                f"({b['start']-base}-{b['end']-base}m)")

    # --- per-venue utilization + idle gaps ---
    def hhmm(m: int) -> str:
        return f"{m // 60:02d}:{m % 60:02d}"

    print(f"Makespan: {hhmm(base)}-{hhmm(end)} = {makespan} min, {len(events)} events, "
          f"{len(by_venue)} venues")
    print()
    print(f"{'venue':<20}{'busy':>6}{'span':>6}{'util':>6}  idle gaps")
    for venue in sorted(by_venue):
        evs = by_venue[venue]
        busy = sum(ev["dur"] for ev in evs)
        span = evs[-1]["end"] - evs[0]["start"]
        util = f"{(100 * busy / span):.0f}%" if span else "n/a"
        gaps = []
        for a, b in zip(evs, evs[1:]):
            g = b["start"] - a["end"]
            if g >= args.gap:
                gaps.append(f"{hhmm(a['end'])}-{hhmm(b['start'])}({g}m)")
        lead = evs[0]["start"] - base
        if lead >= args.gap:
            gaps.insert(0, f"start@{hhmm(evs[0]['start'])}(+{lead}m late)")
        print(f"{venue:<20}{busy:>6}{span:>6}{util:>6}  {', '.join(gaps) or '-'}")

    # --- parallelism across 5-min slots ---
    nslots = math.ceil(makespan / 5)
    conc = []
    for k in range(nslots):
        t = base + k * 5
        conc.append(sum(1 for ev in events if ev["start"] <= t < ev["end"]))
    if conc:
        print()
        print(f"Concurrency: max {max(conc)} venues, "
              f"avg {sum(conc)/len(conc):.1f} active per 5-min slot")

    # --- track heat spacing: starter team needs time on a start-position change,
    # and hurdle heats need time to reconfigure. Same-distance flat heats can run
    # back-to-back, so only flag short gaps where one of those two triggers applies.
    def _base_dist(t: str) -> int | None:
        m = re.match(r"(\d+)m", t)
        return int(m.group(1)) if m else None

    track = sorted((ev for ev in events if ev["venue"] == "track"),
                   key=lambda x: x["start"])
    tight: list[str] = []
    for a, b in zip(track, track[1:]):
        gap = b["start"] - a["end"]
        if gap >= 5:
            continue
        pos_change = _base_dist(a["type"]) != _base_dist(b["type"])
        both_hurdle = "hekk" in a["type"] and "hekk" in b["type"]
        if not (pos_change or both_hurdle):
            continue  # same-distance flat heats may be back-to-back
        reason = "start-position change" if pos_change else "hurdle reconfigure"
        tight.append(f"{a['id']} ends {hhmm(a['end'])}, {b['id']} starts "
                     f"{hhmm(b['start'])} — {gap}m gap, need >=5 ({reason})")
    if tight:
        print(f"\nTRACK SPACING ({len(tight)}) — leave >=5 min on a start-position "
              f"change or between hurdle heats:")
        for t in tight:
            print(f"  - {t}")
    elif track:
        print("\nTrack spacing OK.")

    # --- field reconfig spacing: swapping implements/runway setup at a venue takes
    # time, and a shared-personnel bucket reconfigures whenever it moves to a new
    # event type (even across venues). Same-type groups run back-to-back. Track heats
    # are covered above. Without --shared, only same-venue type changes are checked.
    field = [ev for ev in events if ev["venue"] != "track"]
    streams: list[list[dict]] = []
    claimed: set[int] = set()
    for labels in _resolve_shared(args.shared):
        stream = [ev for ev in field if ev["type"] in labels]
        if len(stream) >= 2:
            streams.append(stream)
            claimed.update(id(ev) for ev in stream)
    rest_by_venue: dict[str, list[dict]] = defaultdict(list)
    for ev in field:
        if id(ev) not in claimed:
            rest_by_venue[ev["venue"]].append(ev)
    streams.extend(evs for evs in rest_by_venue.values() if len(evs) >= 2)

    reconf: list[str] = []
    for evs in streams:
        evs = sorted(evs, key=lambda x: x["start"])
        for a, b in zip(evs, evs[1:]):
            gap = b["start"] - a["end"]
            if a["type"] == b["type"] or not (0 <= gap < 5):
                continue
            reconf.append(f"{a['id']} ({a['type']}) ends {hhmm(a['end'])}, "
                          f"{b['id']} ({b['type']}) starts {hhmm(b['start'])} — "
                          f"{gap}m gap, need >=5 to reconfigure")
    if reconf:
        print(f"\nFIELD RECONFIG SPACING ({len(reconf)}) — leave >=5 min when the "
              f"event type changes at a venue or shared bucket:")
        for r in reconf:
            print(f"  - {r}")
    elif field:
        print("\nField reconfig spacing OK.")

    if warnings:
        print("\nPRE-CHECK WARNINGS (fix before from-events):")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("\nPre-checks OK (still run from-events for shared-venue/track rules).")

    if args.xlsx:
        conflicts, age, recovery = _xlsx_checks(args.csv, args)
        if conflicts:
            print(f"\nATHLETE CONFLICTS ({len(conflicts)}) — move one event in each pair:")
            for c in conflicts:
                print(f"  - {c}")
        else:
            print("\nNo athlete conflicts.")
        if age:
            print(f"\nAGE-MERGE VIOLATIONS ({len(age)}) — re-split the row's categories:")
            for a in age:
                print(f"  - {a}")
        else:
            print("No age-merge violations.")
        fails = [r for r in recovery if r.startswith("FAIL")]
        warns = [r for r in recovery if r.startswith("warn")]
        if fails:
            print(f"\nRECOVERY VIOLATIONS ({len(fails)}) — 13+ need >=10 min between events:")
            for r in fails:
                print(f"  - {r}")
        else:
            print("No recovery violations.")
        if warns:
            print(f"\nRECOVERY WARNINGS ({len(warns)}) — 15+ prefer >=15 min:")
            for r in warns:
                print(f"  - {r}")


if __name__ == "__main__":
    main()
