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
  hard constraint and may make tight schedules infeasible.

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
See `_get_event_group_sort_key`.

This ordering minimizes equipment moves and starting position changes.

#### Spacing between consecutive track events
Implemented in `_track_min_gap_slots` (shared by the spacing constraints and the
Phase 4 pull-forward pass, so both agree how close two events may sit):
- **Hurdle setup/teardown** (one side is hurdles, the other is not, or a hurdle
  distance/position changes): **2 slots**. A 400m cannot start until the hurdles
  are cleared from the straight.
- **Pure start-position change** (different distance-to-goal block, no hurdles):
  **1 slot** — just a starter move.
- **Both groups young (≤12)**: **0 slots** — back-to-back is fine.
- **Otherwise**: **1 slot** of prep time.
- **Sprint→round re-rig**: arena-specific (`ArenaConfig.sprint_to_round_gap_minutes`).

Start positions are grouped by distance-to-goal in `_START_POSITION_BLOCKS`
(e.g. 200m/200mH/600m/5000m share one position, so no extra gap between them).

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
- **Solver note**: the Z3 grouping path (`schedule` command, `--mix-hurdle-distances`)
  still uses the older, more conservative `mixed_hurdle_lane_capacity` (2 gutter lanes
  per distance boundary). It therefore splits mixed-distance pools into more heats than
  strictly necessary, but its output still satisfies the validator above.

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

## Field Event Merging

Field events from similar age groups can be merged into a single event group that runs sequentially sharing equipment.

### Why Merge?
- **Rest between attempts**: With 4-8 athletes, each person gets ~3-5 minutes between their attempts
- **Avoid rapid-fire**: A solo athlete would have attempts back-to-back with no recovery
- **Equipment efficiency**: One setup serves multiple categories

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
