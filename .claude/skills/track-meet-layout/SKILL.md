---
name: track-meet-layout
description: Lay out a track-and-field meet timetable into a schedule_events.csv for the opentrack scheduler, packing events to avoid venue and athlete conflicts with an efficient, well-merged layout. Use when building or adjusting a meet schedule by hand instead of (or after) the Z3 solver, when resolving scheduling conflicts, compacting a timetable, or whenever the user mentions schedule_events.csv, the `from-events` command, event/heat layout, or scheduling a track meet from an Isonen participant XLSX.
---

# Track-meet event-schedule layout

Produce a valid, compact `schedule_events.csv` (one row per event group with start/end
times) by hand, validating every change with `opentrack scheduler from-events` and
iterating until it passes and the layout is tight.

Run all commands from the repo root with `uv run` (the scheduler is a `uv` project; see
the `/python` skill).

## How it works

- **Merging is yours to decide.** The XLSX holds individual athlete entries; the atom is
  one `(event_type, category)` like "60m J13". Putting several categories in one CSV row
  means they run together at one time/venue. You choose the merges by judgment (see the
  guide's merging heuristic); the tools only check them, they don't suggest them.
- **`from-events` is the authoritative oracle.** It breaks each row into atoms and checks
  coverage, per-athlete and per-venue conflicts, track ordering and the age-merge rules.
  It does not impose a grouping, and it stops at the **first** violation. `layout_report.py`
  is the same idea as a fast local detector that surfaces all problems at once.
- **The `start_time`..`end_time` window is what matters** for conflicts; starts sit on a
  5-minute grid. `event_group_id` is just a label and `duration_minutes` is optional.
- **Meet constraints come from the user, not the data.** `--arena`, `--date`, `--shared`
  (officials sharing a venue) and `--sticky` (no event-type interleaving) define what a
  *valid* schedule is and are enforced by `from-events`. Establish them up front and pass
  them to every `from-events` run. The seed only needs `--arena`/`--date` (what changes
  which atoms and venues exist); it does the layout work in your hands, so it takes no
  other knobs.

Read [references/layout-guide.md](references/layout-guide.md) for the details: the CSV
contract, venue/parallelism map, merge + age rules, error catalog, layout heuristics,
soft goals, and flags. Keep it open while working.

## Workflow

1. **Propose** a starting layout (default merges, every venue parallel from 17:00, no
   solver). The merges are a starting point — re-merge freely.
   ```bash
   uv run python .claude/skills/track-meet-layout/scripts/dump_groups.py \
       <participants.xlsx> --arena <arena> [--date DD.MM.YYYY] -o schedule_events.csv
   ```

2. **Detect mistakes** — list every athlete conflict, age-merge violation, short track
   gap, short field reconfig gap and off-grid start at once:
   ```bash
   uv run python .claude/skills/track-meet-layout/scripts/layout_report.py \
       schedule_events.csv --xlsx <participants.xlsx> --arena <arena> [--date ...] \
       [--shared jt,dt,ht ...]
   ```
   Pass the same `--shared` groups you give `from-events` so cross-venue reconfig gaps
   are checked. The tool detects problems; it does not design the layout. Deciding
   merges and placement is your judgment (see the guide's heuristics).

3. **Edit** times and merges to fix what the tool flagged and to compact. You decide
   the merges (right-size groups to ~4-8 per the guide's merging heuristic and age
   rules); the tool then tells you if a merge is illegal or creates a conflict. Also
   **compress the track, but leave >=5 min between heats on a start-position change or
   between hurdle heats** (starter repositioning / hurdle reconfiguring), and **leave
   >=5 min on the field when the event type changes at a venue or shared bucket**
   (Spyd -> Slegge: implements/runway reset). Re-run the report after each batch of edits.

4. **Validate** with the oracle, passing **all** the meet constraints:
   ```bash
   uv run opentrack scheduler from-events <participants.xlsx> schedule_events.csv \
       -o schedule.html --arena <arena> [--date ...] \
       [--shared jt,dt,ht ...] [--sticky/--no-sticky]
   ```
   Fix the single violation it reports, then run it again.

5. **Iterate** steps 2-4 until `from-events` prints `All constraints validated
   successfully` and the makespan/concurrency in `layout_report.py` are good.

## Files

- `scripts/dump_groups.py` — emit a starting layout (proposed merges, venues parallel).
- `scripts/layout_report.py` — mistake detector + compactness metrics: athlete conflicts,
  age-merge violations, track-spacing gaps, field reconfig gaps, off-grid starts, idle
  gaps, concurrency.
- `references/layout-guide.md` — CSV contract, venue model, merge + age rules, error
  catalog, heuristics, soft goals, flags.
- `scheduler/CONSTRAINTS.md` (repo) — background on constraints and merge rationale.
