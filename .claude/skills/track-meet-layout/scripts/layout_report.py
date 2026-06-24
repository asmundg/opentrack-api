#!/usr/bin/env python3
"""Detect mistakes and report compactness for a schedule_events.csv.

This is a conflict/quality detector, not a layout designer. Deciding merges and
placement is the agent's job (see the skill's heuristics); this tool only tells you
what is wrong and how tight the result is. `from-events` is the authoritative gate but
stops at the FIRST violation; this surfaces ALL problems at once and adds compactness
metrics:
  - makespan, per-venue utilization, idle gaps (compaction opportunities), parallelism
  - cheap local pre-checks: 5-min slot alignment, same-venue overlaps
  - shared-bucket overlaps: two different shared-personnel event types running at the
    same time across their separate venues (pass the same --shared groups)
  - venue stickiness: an event type reappearing at a venue/shared bucket after a
    different type ran in between (mirrors from-events --sticky)
  - track-heat spacing (>=5 min on a start-position change or between hurdle heats)
  - field reconfig spacing (>=5 min when the event type changes at a venue/shared
    bucket; pass the same --shared groups you give from-events to catch cross-venue
    transitions like Spyd -> Slegge)
  - with --xlsx: EVERY athlete double-booking and age-merge violation at once, plus a
    GROUP SIZING table (athletes + scheduler-computed slot duration per row)

It does NOT replace `from-events` (track ordering and the authoritative gate live
there), but it now covers the shared-venue and stickiness rules locally so you can fix
them in batch before spending a from-events round-trip.

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


def _stream_overlaps(stream: list[dict], hhmm) -> list[str]:
    """Overlap messages for events sharing one conflict bucket (sorted by start)."""
    evs = sorted(stream, key=lambda x: x["start"])
    out: list[str] = []
    for a, b in zip(evs, evs[1:]):
        if b["start"] < a["end"]:
            out.append(f"{a['id']} ({a['type']}, {hhmm(a['start'])}-{hhmm(a['end'])}) "
                       f"overlaps {b['id']} ({b['type']}, "
                       f"{hhmm(b['start'])}-{hhmm(b['end'])})")
    return out


def _stream_sticky(stream: list[dict], hhmm) -> list[str]:
    """Stickiness messages: a type reappears after a different type ran in between.

    Mirrors constraint_validator._validate_venue_stickiness so the batch view and the
    authoritative gate never drift.
    """
    evs = sorted(stream, key=lambda x: x["start"])
    out: list[str] = []
    seen: dict[str, int] = {}
    for idx, ev in enumerate(evs):
        t = ev["type"]
        if t in seen and seen[t] != idx - 1:
            offender = evs[seen[t] + 1]
            out.append(
                f"{t} runs at {hhmm(evs[seen[t]]['start'])} and again at "
                f"{hhmm(ev['start'])} ({ev['id']}), with {offender['type']} "
                f"({offender['id']}) at {hhmm(offender['start'])} in between")
        seen[t] = idx
    return out


def _xlsx_checks(csv_path: Path, args) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return (athlete_conflicts, age_violations, recovery, sizing) for the layout.

    Athlete membership is taken from the CSV's own merges (each row's categories),
    matching exactly what from-events validates. Reuses the validator's age rules so
    this batch view and the authoritative gate never drift. ``sizing`` is one
    human-readable line per row with the athlete count and the scheduler-computed slot
    duration, so re-merged rows don't need a hand-computed end_time.
    """
    if (_REPO_ROOT / "scheduler").is_dir():
        sys.path.insert(0, str(_REPO_ROOT))
    from scheduler import models
    from scheduler.isonen_parser import parse_isonen_xlsx
    from scheduler.event_csv import import_event_overview_csv
    from scheduler.constraint_validator import age_merge_errors, _atom_counts
    from scheduler.models import (
        Category, EventGroup, EventType, EventVenueMapping, Venue,
        get_category_age_order,
    )

    if args.arena not in models.ARENAS:
        sys.exit(f"Unknown arena '{args.arena}'")
    models.ARENA = models.ARENAS[args.arena]
    models.ACTIVE_SECONDARY_VENUES = {
        EventType[n] for n in models.ARENA.default_secondary_venues
    }
    events, athletes = parse_isonen_xlsx(str(args.xlsx), filter_date=args.date)
    rows = import_event_overview_csv(csv_path)

    counts = _atom_counts(athletes)
    age = age_merge_errors(rows, counts)

    # Per-row sizing: athletes in the merge + the duration the scheduler would assign
    # (built from the same Event objects/EventGroup as dump_groups, so it matches what
    # from-events expects). Flags rows whose CSV window is shorter than the computed
    # slot duration, and track merges over the 8-lane cap.
    events_by_atom: dict[tuple[EventType, Category], object] = {}
    for e in events:
        events_by_atom[(e.event_type, e.age_category)] = e
    sizing: list[str] = []
    for r in rows:
        atoms = []
        for raw in r.categories.split(","):
            name = raw.strip()
            if not name:
                continue
            try:
                atoms.append((r.event_type, Category(name)))
            except ValueError:
                continue
        grp_events = [events_by_atom[a] for a in atoms if a in events_by_atom]
        n_ath = sum(counts.get(a, 0) for a in atoms)
        if grp_events:
            calc = EventGroup(
                id=r.event_group_id, event_type=r.event_type, events=grp_events
            ).duration_minutes
        else:
            calc = 0
        slot = math.ceil(calc / 5) * 5 if calc else 0
        window = _mins(r.end_time.strftime("%H:%M")) - _mins(r.start_time.strftime("%H:%M"))
        flags = []
        if slot and window < slot:
            flags.append(f"window {window}m < needs {slot}m")
        is_track = EventVenueMapping.get(r.event_type) == Venue.TRACK
        if is_track and n_ath > 8:
            flags.append(f"{n_ath} athletes > 8-lane cap (split)")
        flag = ("  ⚠️ " + "; ".join(flags)) if flags else ""
        sizing.append(
            f"{r.event_group_id:<34} {n_ath:>3} ath  slot={slot:>3}m  "
            f"window={window:>3}m{flag}")

    conflicts: list[str] = []
    recovery: list[str] = []
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

    return conflicts, age, recovery, sizing


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

    # --- shared-bucket overlaps + venue stickiness: mirror from-events conflict
    # buckets (get_scheduling_venue_keys). A shared-personnel group is one serial
    # stream across its separate venues, so two of its types running at once is a hard
    # conflict; and each type must stay contiguous per venue / shared bucket (--sticky).
    shared_groups = _resolve_shared(args.shared)
    shared_conflicts: list[str] = []
    for labels in shared_groups:
        stream = [ev for ev in events if ev["type"] in labels]
        shared_conflicts.extend(_stream_overlaps(stream, hhmm))
    if shared_conflicts:
        print(f"\nSHARED-BUCKET CONFLICTS ({len(shared_conflicts)}) — one shared "
              f"officials team cannot run two events at once:")
        for c in shared_conflicts:
            print(f"  - {c}")

    sticky_buckets: dict[str, list[dict]] = {}
    for venue, evs in by_venue.items():
        if venue == "track":
            continue
        sticky_buckets[venue] = evs
    for labels in shared_groups:
        sticky_buckets["shared:" + ",".join(sorted(labels))] = [
            ev for ev in events if ev["type"] in labels]
    sticky: list[str] = []
    for name, evs in sticky_buckets.items():
        for msg in _stream_sticky(evs, hhmm):
            sticky.append(f"{name}: {msg}")
    if sticky:
        print(f"\nVENUE STICKINESS ({len(sticky)}) — keep each event type contiguous "
              f"per venue/shared bucket (no A-B-A interleaving):")
        for s in sticky:
            print(f"  - {s}")

    if warnings:
        print("\nPRE-CHECK WARNINGS (fix before from-events):")
        for w in warnings:
            print(f"  - {w}")
    if not (warnings or shared_conflicts or sticky):
        print("\nStructural pre-checks OK (slot alignment, venue + shared-bucket "
              "overlaps, stickiness, spacing). Run from-events for track ordering and "
              "the authoritative gate; athlete conflicts are listed below if --xlsx.")

    if args.xlsx:
        conflicts, age, recovery, sizing = _xlsx_checks(args.csv, args)
        if sizing:
            print(f"\nGROUP SIZING ({len(sizing)}) — athletes + scheduler slot "
                  f"duration per row (set end_time to start + slot):")
            for s in sizing:
                print(f"  {s}")
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
