# Layout guide: CSV contract, venues, merging, heuristics, validation

The practical playbook for laying out `schedule_events.csv` by hand. Background on the
constraint and merge rationale lives in `scheduler/CONSTRAINTS.md`.

## Contents
- [CSV contract](#csv-contract)
- [Venue & parallelism model](#venue--parallelism-model)
- [Merging model & age rules](#merging-model)
- [Error catalog](#error-catalog)
- [Layout heuristics](#layout-heuristics)
- [Soft goals](#soft-goals)
- [Validation strategy](#validation-strategy)
- [Flags](#flags)

## CSV contract

Columns: `event_group_id,event_type,categories,venue,start_time,end_time[,duration_minutes]`.

- You control which categories share a row (`categories`), the `venue`, and the
  `start_time`/`end_time` window. The window is the authoritative occupancy used for all
  conflict checks.
- `event_group_id` is just a unique label; name re-merged rows however you like.
- Pick a real `venue` for the event type (see the venue map below).
- `duration_minutes` is **optional and reference-only** — derived from the window. You
  may omit the column entirely.
- `start_time` must sit on a **5-minute boundary** relative to the earliest event, or
  `from-events` crashes at build. `end_time` need not be on a boundary.
- Set `end_time = start_time +` the event's real running time. Bigger field merges run
  longer (roughly the sum of per-category times); the proposal seed computes correct
  windows, so mirror its sizing when you re-merge.
- The meet start time = the **earliest** `start_time` in the file.

## Venue & parallelism model

Events sharing a venue cannot overlap; different venues run in parallel. Map of
event type -> venue (from `models.EventVenueMapping`):

- `track`: every running event (60m..3000m, all hurdles). All heats are serial on
  one timeline, ordered by distance (see heuristics).
- `throwing_circle`: Diskos (dt) + Slegge (ht) share it.
- `shot_put_circle`: Kule (sp). `shot_put_circle_2` is a secondary circle.
- `javelin_area`: Spyd (jt) + Liten ball (bt).
- `jumping_pit`: Lengde (lj) + Tresteg (tj) + standing long.
- `high_jump_area`: Høyde (hj) + Stavsprang (pv), unless the arena gives PV its own
  `pole_vault_area` (valhall does; tromsohallen does not).

Two parallelism levers:
- **Secondary venues** (arena default; tromsohallen = `hj,sp`): the youngest
  (J/G-Rekrutt) run at `*_2` venues in parallel with the primary.
- **`--shared` groups** fold several types onto one conflict bucket so they can NOT
  run in parallel even across venues (e.g. `--shared jt,dt,ht` when officials are
  scarce). The seed lays venues out independently, so a `--shared` set will show as a
  shared-bucket conflict only in `from-events` — fix by serialising those types. A
  shared bucket is one serial stream: order its events to keep each type contiguous
  and leave a >=5 min reconfig gap whenever the type changes (see heuristic 3).
- **`--sticky`** (default on): one event type must form a contiguous block per
  venue (no DT-HT-DT). Track is exempt.

## Merging model

Merging is a **layout decision you make in the CSV**. The atom is one
`(event_type, category)` like "60m J13" (one per category with entries). Listing
several categories in one row means they run together at one time/venue. `from-events`
breaks every row back into atoms and validates whatever you wrote; it does not impose
a grouping. You can split a row, combine rows, or move a category between rows at will.

Why merge at all:
- A field group of 4-8 athletes gives each athlete rest between attempts and shares
  one equipment setup. A solo athlete gets rapid-fire attempts; a huge group runs long.
- Merging frees venue time (one row instead of several) which helps compaction.

A row is one window: every athlete in it is busy for the **whole** window, so a wide
merged field group blocks all its athletes for that span (watch for conflicts with
their other events).

### Age-merge rules (enforced by from-events)

**Field events have no age restrictions: a row may merge any categories** (Rekrutt
through Masters together is allowed). Oversize groups (> 8 athletes) only get a
warning, since field events run sequentially.

**Track heats** must obey these or `from-events` reports an `Age merge violation`:

- **Rekrutt** (J/G-Rekrutt, the 10-year-olds) never share a heat with any older
  category.
- **11-14** never share a heat with **15+** (15-17, 18-19, Senior or Masters).
- at most **8** athletes per heat (lane cap).
- **Hurdles:** may mix distances and heights. Each distinct hurdle setup — a unique
  (distance, height) pair — needs an empty gutter lane between it and the next, so
  capacity is `usable_lanes - (distinct_setups - 1)` (see `scheduler/CONSTRAINTS.md`
  section 4). Categories sharing the exact same setup pack with no gutter between them.

Gender is not enforced: you may merge boys and girls in a row if you choose.

### Choosing groups (merging heuristic)

The seed proposes merges by age tier; treat them as a starting point and adjust by
hand. Aim for **~4-8 athletes per group** so field athletes get rest between attempts
and heats fill the lanes; avoid singletons and pairs **when a legal partner exists**.
Decide each event type's groups like this:

- **Field events** (throws, jumps): combine neighbouring categories up to ~8, in age
  order. Any ages may share (Rekrutt..Masters), but prefer adjacent groups (e.g.
  13+14, or 15-17 together) so the field cards stay tidy. Exceeding 8 is allowed when
  the alternative is a stranded single (it only warns).
- **Track flat** (60m, 100m, 200m, 400m, 600m, ...): combine categories within the age
  rules above (Rekrutt alone; 11-14 together; 15+ together; never 11-14 with 15+),
  totalling ≤8 athletes. Genders may mix.
- **Hurdles**: combine within lane capacity. Distances and heights may both mix; each
  distinct (distance, height) setup costs a gutter lane, so capacity is
  `lanes - (distinct_setups - 1)`. E.g. with 8 lanes, four setups leave 5 athlete
  lanes. Stay within the age rules (hurdles are track events). Merging hurdle heats of
  different distances cuts the number of heats (and the reconfigure gaps between them),
  so it is often worth doing when the lanes fit.
- **No legal partner**: keep the group as-is (a single senior thrower, the only 100m
  hekk entry, a hurdle category that would overflow the lanes if merged). Do not force
  an illegal or over-capacity merge just to avoid a single.

This is your judgment call. `layout_report.py`/`from-events` do not suggest merges;
they only tell you when a merge you made is illegal (age rule, lane capacity) or
creates a conflict. Make the merge, then check.

## Error catalog

Real `from-events` messages, their cause, and the fix. It stops at the **first**
violation, so fix one and re-run. Track age-ordering and oversized field groups are
**warnings**, not failures.

| Message | Cause | Fix |
| --- | --- | --- |
| `Missing schedule entries for: <type> <cat>` | an atom (event_type+category) has no row | add it to a row |
| `Row X schedules <type> <cat>, which has no registered athletes` | a row lists a category with no entries | remove that category |
| `<type> <cat> is scheduled twice` | the same atom appears in two rows | keep it in one row |
| `Venue conflict at <venue>: A overlaps with B` | two rows share a venue/`--shared` bucket and overlap | move one later, or serialise the shared types |
| `Venue stickiness violated at <venue>: ...` | a type is interleaved at a venue (`--sticky`) | make each type a contiguous block per venue |
| `Athlete conflict for <name>: A overlaps with B` | someone is in two overlapping rows | move A or B, or re-merge so they share a row |
| `Track event ordering violation: ...` | track distances out of order (and not the Rekrutt round-race exception) | reorder track times into distance order |
| `Age merge violation in X: ...` | a track heat mixes categories that may not run together | re-split the heat's categories (see age rules above) |
| `Hurdle heat X has N athletes but only K usable lanes` | hurdle merge exceeds lane capacity after gutter lanes | split the heat or drop a setup |
| `... does not align with 5-minute slot boundaries` (traceback) | a `start_time` is off the grid | snap every start to :00/:05/:10/... |

## Layout heuristics

Start from the proposal seed (all venues parallel from the start time). It has no venue
conflicts and correct track order, but athlete double-bookings and seed-default merges.
Then:

1. **Decide the groups** using the merging heuristic above. Adjust the seed's merges by
   hand: right-size field and flat-track groups toward 4-8, merge hurdle heats where the
   lanes fit (fewer heats = fewer reconfigure gaps), and leave lone categories alone.
   This is judgment, not a tool step — make the merges you think are right, then let the
   checks below catch mistakes.
2. **Keep the track chain ordered.** All track rows, sorted by start time, must be in
   `TRACK_DISTANCE_ORDER`: 60m, 60m hekk, 80m hekk, 100m, 100m hekk, 150m, 200m,
   200m hekk, 600m, 5000m, 300m, 1500m, 3000m, 400m, 800m. Younger-first within a
   distance is soft (warning only). When you move a track heat, move it within the
   chain, not across a different distance. **Exception:** a Rekrutt (10-year-old) round
   race (e.g. their 400m) may run out of order — typically first, on a clear track
   before the hurdles are set up — so the youngest finish early. `from-events` allows
   this with a warning. It pushes the hurdle block back by the hurdle setup time
   (~10 min), which is usually worth it for the kids.
3. **Space track heats only where needed.** Compress the track timeline, but leave a
   >=5 min gap between two consecutive track heats when the **start position changes**
   (a different race distance — one starter team must walk to the new start) or when
   **both heats use hurdles** (time to reconfigure the hurdles). Consecutive
   same-distance flat heats can run back-to-back. The same reconfiguration logic
   applies on the **field**: leave >=5 min whenever the event **type changes** at a
   venue or within a `--shared` personnel bucket (Liten ball -> Spyd, Spyd -> Slegge,
   Slegge -> Diskos), because implements and the runway/circle must be reset and the
   team may have to walk to another venue. Two groups of the **same** type (two Spyd
   groups) run back-to-back. This compounds: a bucket of N distinct types has N-1
   reconfig gaps it cannot avoid, and each gap rounds up to the 5-min grid, so a
   five-type throws bucket costs ~20-30 idle minutes on top of the events themselves.
4. **Detect mistakes** with `layout_report.py --xlsx`. It lists, all at once: athlete
   conflicts (two overlapping rows sharing an athlete), age-merge violations, track
   spacing gaps that are too short, field reconfig gaps that are too short (pass the
   same `--shared` groups you give `from-events` so cross-venue transitions are seen),
   off-grid starts, and same-venue overlaps. Fix each:
   - athlete conflict → move one of the two rows to a non-overlapping slot, or re-merge
     so the clashing categories no longer share an overlap;
   - age/hurdle violation → re-split the offending row per the merge rules;
   - short track or field gap → widen it to >=5 min.
   Prefer moving the row whose venue timeline has the most slack (idle gaps in the
   report) and that does not disturb the track distance chain.
5. **Re-check after every batch of edits** (a move or re-merge can create a new venue
   overlap or athlete conflict). `layout_report.py` is fast; use it between
   `from-events` runs.
6. **Compact.** The report prints idle gaps per venue and concurrency. Pull rows
   earlier into gaps when it introduces no conflict. Target: high concurrency (4-6
   venues active), small makespan, while respecting the track spacing above.

Times are on a 5-minute grid relative to the earliest event. Move rows by whole
5-minute steps. Set `end_time = start_time +` the group's real running time (it grows
when you merge more categories into a field group).

## Soft goals

Optimise only after the schedule is valid and reasonably tight, in this order
(from `scheduler/CONSTRAINTS.md`):

1. **Young finish first.** J/G-Rekrutt (10yo) should end earliest, then 11/12. Place
   their rows in the first slots and keep them off late timelines.
2. **Recovery gaps.** For athletes 13+ with multiple events, leave several idle slots
   between their rows. Maximise the smallest such gap across athletes; do not spend
   makespan you do not have.

## Validation strategy

`from-events` is the only authoritative gate and it stops at the **first** violation.
So:

- Use `layout_report.py --xlsx` to clear ALL athlete conflicts, same-venue overlaps,
  age-merge violations and short reconfig gaps in batch first (cheap, lists
  everything). Give it the same `--shared` groups as `from-events` so it checks
  cross-venue reconfig gaps too.
- Then run `from-events`. It additionally enforces track ordering, `--shared` buckets,
  `--sticky` and full coverage (every atom placed exactly once). Fix the one violation
  it reports, then run it again.
- Repeat until it prints `All constraints validated successfully`. A clean run also
  writes the HTML and (for the full pipeline) the athlete CSV.
- Always give `from-events` the full set of meet constraints (`--arena`, `--date`,
  `--shared`, `--sticky`). The seed only used `--arena`/`--date`, so the others first take
  effect here — a missing `--shared` or `--sticky` will pass validation but produce a
  schedule the venue cannot actually run.

## Flags

These are **meet constraints**: they define what a valid schedule is, you get them from
the user up front, and `from-events` enforces them. The seed (`dump_groups.py`) only
reads `--arena` and `--date` (they change which atoms and venues exist); the rest are
validation-time only, so pass them to `from-events` on every run.

| Flag | Seed | from-events | Meaning |
| --- | --- | --- | --- |
| `--arena {generic,tromsohallen,valhall}` | yes | yes | lane limits, hurdle markers, secondary venues, PV separation |
| `--date DD.MM.YYYY` | yes | yes | filter a multi-day meet to one day |
| `--shared a,b,c` (repeatable) | no | yes | event types sharing officials/equipment; cannot run in parallel |
| `--sticky / --no-sticky` | no | yes | force each event type into a contiguous block per venue (default on) |

Gender is **not** a constraint: `from-events` never checks it, so a heat may mix boys and
girls. The seed merges genders in track heats by default (splitting only where that would
cross the 11-14/15+ age boundary). Split or merge genders yourself as the layout needs.
