# Scheduler Constraints and Optimization Goals

This document defines the rules and tradeoffs for the track meet scheduler.

## Hard Constraints

These must always be satisfied - the scheduler will fail if it cannot meet them.

### 1. Venue Exclusivity
Only one event can use a venue at any given time slot.
- Track events share the track
- Field events use dedicated areas (shot put circle, jumping pit, etc.)
- Secondary venues (e.g., shot put circle 2) can run in parallel with primary venues
- **Shared venue groups** (CLI `--shared`): event types that share officials or
  equipment can be folded onto a shared conflict bucket via the CLI. For example,
  `--shared jt,dt,ht` makes javelin, discus, and hammer mutually exclusive even
  though they live in different physical venues. The flag can be repeated for
  several groups (e.g., also `--shared hj,lj`). The shared bucket is *additive*:
  events stay in their natural-venue bucket too, so `--shared hj,lj` does not
  let Lengde overlap with Tresteg at the jumping pit. Secondary venues still
  apply within their own bucket.
- **Venue stickiness** (CLI `--sticky`): when enabled, events of the same type
  at the same scheduling venue key must run as a contiguous block. This forbids
  patterns like DT-HT-DT at the throwing circle and respects shared groups
  (e.g., with `--shared jt,dt,ht --sticky`, the throws form three back-to-back
  type blocks across the throwing circle and javelin area). Track is exempt
  because its precedence rules already determine event order. Stickiness is a
  hard constraint and may make tight schedules infeasible. Lengde and
  Høyde are exempt (`NON_STICKY_EVENT_TYPES`): they may recur with other types
  in between (Høyde split around Høyde uten tilløp, Lengde around Tresteg),
  while every other type still forms one block.

### 2. Athlete Conflicts
An athlete cannot compete in two events simultaneously. If an athlete is registered for multiple events, those events must not overlap.

### 3. Track Event Ordering
Track events follow a strict sequence based on starting position logistics:
1. **By distance** - Shorter distances first (starter team moves counter-clockwise)
2. **Hurdles after flat** - Within same distance block, flat races before hurdles
3. **By age** - Youngest to oldest within each distance/hurdles
   block. This is a soft policy and we can diverge from it when
   needed.

**Rekrutt round-event exception**: a Rekrutt (10-year-old) round race (e.g. a
400m) runs right after the sprint/hurdle block instead of being forced last by
its distance, so the youngest finish early. Sprints/hurdles still come first
overall — they occupy the home straight that the round race must run through.
Distance order is enforced by `constraint_validator._validate_track_ordering`
(using `get_track_event_order`), with the Rekrutt round-event exception allowed
as a warning. Younger-first within a distance is a soft policy, not enforced.

**Same-distance swap**: `from-events --swap-same-distance` lets flat and hurdle
races over one distance run in either order for a single meet (60m with 60m and
80m hekk, 100m with 100m hekk, 200m with 200m hekk, per
`HURDLES_BASE_DISTANCE`). Use it to keep the straight hurdles in one block, e.g.
100m hekk before 100m. Different distances stay in order.

This ordering minimizes equipment moves and starting position changes. Relays
run last, after the individual races.

#### Relays
Relay classes (`4x60m stafett`) are contested by teams, so a heat holds one team
per lane, not one athlete: three 4-person teams are a heat of 3. The parser
counts teams via the `Lag` column and records it as `Event.entries`; the age-merge
rules apply as for any track heat, with the relay classes slotted by age
(`Stafett 6-10` counts as Rekrutt, `Stafett 11-12`/`Stafett 13-14` as 11-14).

Relay teams are **team registrations** in Isonen, so they live in
`publicEvent.teams`, not `publicEvent.participants`, and the manual
"Deltakerliste" XLSX export omits them entirely. A team that has not named its
runners yet still gets a row (team name only) so its heat is scheduled.

#### Spacing between consecutive track events
Spacing is a soft layout goal, checked by the track-meet-layout skill's
`layout_report.py` (in minutes), not a hard `from-events` constraint. Compress
the track timeline, but leave **>=5 min** between two consecutive heats when:
- **The start position changes** (a different race distance): the starter team
  must walk to the new start. A 400m also cannot start until the hurdles are
  cleared from the straight.
- **Hurdles are reconfigured** (both heats use hurdles, or a hurdle setup
  changes): time to reset the hurdles.

Consecutive same-distance flat heats can run back-to-back. Races that share a
start position (e.g. 200m/600m/5000m at the 200m-to-goal mark) need no extra gap.

On the **field**, leave the same **>=5 min** when the event type changes at a
venue or within a shared-personnel bucket (e.g. Spyd -> Slegge): implements and
the runway/circle must be reset. Same-type groups run back-to-back. `layout_report.py`
checks this when given the same `--shared` groups as `from-events`.

### 4. Hurdle Event Merging
Hurdle categories may share a heat across different distances and heights, subject to
lane capacity:
- **One gutter per setup**: each distinct hurdle setup — a unique
  `(distance_between_m, height_cm)` pair — needs an empty "gutter" lane between it and
  the next, whether the difference is distance or height. Categories with the exact same
  setup pack with no gutter between them. Capacity is therefore
  `effective_lanes - (num_distinct_setups - 1)` (`hurdle_lane_capacity`), e.g. 8 lanes
  with four setups leaves five athlete lanes. This is the rule the manual-layout
  validator (`from-events`) and the hurdle setup-plan generator enforce.
- **Hard <15 / 15+ boundary**: hurdle events are never pooled across the under-15 / 15+
  age boundary (an 11-14 and a 15+ category never share a heat), even when the lanes
  would fit. This can force single-person heats (e.g. one G14 and one J15 at 80m hurdles)
  that cannot be merged.
- **Seed grouping note**: the proposal seed (`group_events_by_type`, used by the
  skill's `dump_groups.py`) uses the older, more conservative
  `mixed_hurdle_lane_capacity` (2 gutter lanes per distance boundary). It therefore
  splits mixed-distance pools into more heats than strictly necessary, but its output
  still satisfies the validator above, and the agent is free to re-merge.

Hurdle specs (60m / 80m / 100m) are defined in `models.py:HURDLE_SPECS`. Boys 17+ run 110m hurdles, which has no event type and is therefore not modelled.

## Optimization Goals

These are soft goals, optimized in priority order. Later goals only improve if earlier goals are not compromised.

### Priority 1: Minimize Total Duration
Find the shortest possible schedule that satisfies all hard constraints.

### Priority 2: 10-Year-Olds Finish First
Rekrutt (J/G-Rekrutt) athletes should finish as early as possible. Young children have limited attention spans and parents want to leave early.

To make this concrete, Rekrutt field groups run before older groups at the same
venue (`add_youngest_field_precedence`), and Rekrutt track races sort right after
the sprint/hurdle block (see Track Event Ordering). Rekrutt athletes only have
Rekrutt events, so neither rule creates an athlete conflict.

### Priority 3: 11/12-Year-Olds Finish Early
After 10-year-olds, the 11/12 age groups should finish next.

### Priority 4: Maximize Recovery Gaps for Older Athletes
Athletes aged 13+ who have multiple events need adequate recovery time between events. The scheduler maximizes the minimum gap across all such athletes.

Recovery is partly a **hard constraint**, enforced by `constraint_validator.py` (and
`from-events`):

- **13+ athletes must have >= 10 minutes** between any two of their consecutive
  events, or validation **fails**.
- **15+ athletes should have >= 15 minutes**; a shorter (but >= 10 min) gap passes
  with a **warning**.

The gap is measured between one event's `end_time` and the next event's `start_time`
for the same athlete. Younger than 13 has no recovery requirement (the overlap check
still applies to everyone).

`--no-field-recovery` waives the floor for **field-to-field** pairs only, for meets
where the throws and jumps queue on one officials team and the athlete just walks
between venues instead of recovering from an effort. Recovery still applies whenever
a track event is on either side of the gap, and overlaps still fail. Leave it off
unless the meet is actually run that way.

## Field Event Merging

Field events from similar age groups can be merged into a single event group that runs sequentially sharing equipment.

### Event duration and the per-attempt clock

A field group's window is `attempts × minutes-per-attempt`, and the per-attempt
clock depends on how many athletes are in the competition. A shrinking field is
entitled to **more** time per attempt, so halving the entries does not halve the
window:

| Athletes | High jump | Pole vault | Throws, LJ, TJ |
| --- | --- | --- | --- |
| 4+ | 1 min | 1 min | 1 min |
| 2-3 | 1.5 min | 2 min | 1 min |
| 1 | 3 min | 5 min | 2 min (consecutive attempts) |

A lone high jumper therefore needs ~23 minutes, not the ~11 a flat per-athlete
rate would suggest. `EventGroup.duration_minutes` applies this, keyed on the
group's starting size; `attempt_minutes()` in `models.py` holds the table.

### Why Merge?
- **Rest between attempts**: With 4-8 athletes, each person gets ~3-5 minutes between their attempts
- **Avoid rapid-fire**: A solo athlete would have attempts back-to-back with no recovery
- **Equipment efficiency**: One setup serves multiple categories

### Vertical jumps merge by ability, not by convenience

Høyde and stav run **one shared bar progression** for the whole group, so the
usual "any ages may merge" rule does not apply. A group spanning a wide ability
range wastes the venue: the youngest are eliminated long before the oldest enter,
and the bar spends the middle of the competition at heights nobody is jumping.

Merge **adjacent** categories only (G13+G14, J15+J16, J17+KS). Splitting a wide
group into two narrow ones costs venue time but is still the right call. A group
merging categories more than four age tiers apart is flagged by
`layout_report.py` under `AGE-MERGE WARNINGS`.

### Merging Tiers (field)

Field events are grouped into age tiers at each venue; deficient tiers are then
combined conservatively (see "Rule of 4" below):

- **10-year-olds (Rekrutt)**: Separate tier. J/G-Rekrutt merge together, but
  Rekrutt **never** merges with any older tier, even if that leaves a tiny
  group. (Enforced for both field and track in
  `_validate_no_forbidden_combinations`.)
- **11-12 and 13-14 year-olds**: Two youth tiers. Splitting youth at the 12/13
  boundary keeps a self-sufficient younger group (≥4) from being dragged into an
  over-wide span when an older group needs a partner.
- **15+ year-olds**: Merge within this tier (15-17 + 18-19 + Sr), with smart
  unmerging (see below).
- **Masters**: Separate tier; may combine with 15+ when deficient.

### Minimum Preferred Group Size (Rule of 4)

Both field event groups and track heats strongly prefer **≥4 athletes** per
group. When a bucket has fewer, the scheduler attempts cross-tier merges before
settling for a tiny group.

For **track heats**, the merge fires only when the combined size stays ≤8
(hard lane cap). Below 4 with no eligible partner → small heat is accepted.

For **field event groups**, the tiny-bucket rescue is deliberately conservative:
- A bucket that already has ≥4 is **never padded** — so a self-sufficient
  younger group is not pulled into a wider age span.
- Only two **deficient** (<4) buckets are combined, preferring a result in
  [4, 8].
- Rekrutt buckets never participate.
- A leftover one-person bucket is folded into the smallest sibling to avoid a
  solo field event.

The cap of 8 is a SOFT split target. When a merged bucket exceeds 8 and cannot
be partitioned cleanly into [4,8]-sized groups, an oversized group is allowed
and a warning is emitted on stdout (prefixed with ⚠️).

**Hurdle events** are not affected by this rescue pass — they have their own
distance/height/gutter constraints documented in section 4 above.

### The Merging vs Spacing Problem

When categories are merged into a single event group, athletes compete at different times within that event depending on their category's position in the sequence.

**Example**: Aurora (J17) has three field events. If J17 is merged with G17, G18-19, J16 in each event, she might compete:
- Near the END of shot put (J17 is 3rd of 4 categories)
- Near the END of high jump (J17 is 3rd of 4 categories)

The scheduler enforces gaps between event GROUP start/end times, but the actual gap for an athlete depends on when within each event they compete.

**Worst case**: If an athlete is LAST in event A and FIRST in event B, their actual recovery time equals the constraint gap. If they're FIRST in A and LAST in B, they get much more recovery than required. But if the positions vary unpredictably across events, the constraint may not reflect reality.

### Smart Unmerging (Solution)

For 15+ athletes with **multiple field events**, their categories are kept separate (not merged with other categories). This ensures:
- The spacing constraint gap equals the actual athlete recovery time
- Categories without multi-event athletes can still be merged for rest between attempts

**Implementation**: `_get_multi_event_categories_15plus()` identifies categories that must stay separate, and `_create_field_groups()` respects this when building event groups.

## Configuration

### Slot Duration
Default: 5 minutes per slot. All times are quantized to slots.

### Personnel
Not currently used as a constraint (placeholder for future).

### Secondary Venues
Controlled by `ACTIVE_SECONDARY_VENUES` set and `--secondary-venues` CLI flag. When an event type is active, young athletes (J/G10) use secondary venues (e.g., shot put circle 2, high jump area 2) which allows parallel scheduling.
