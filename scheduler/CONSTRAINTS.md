# Scheduler Constraints and Optimization Goals

This document defines the rules and tradeoffs for the track meet scheduler.

## Hard Constraints

These must always be satisfied - the scheduler will fail if it cannot meet them.

### 1. Venue Exclusivity
Only one event can use a venue at any given time slot.
- Track events share the track
- Field events use dedicated areas (shot put circle, jumping pit, etc.)
- Secondary venues (e.g., shot put circle 2) can run in parallel with primary venues

### 2. Athlete Conflicts
An athlete cannot compete in two events simultaneously. If an athlete is registered for multiple events, those events must not overlap.

### 3. Track Event Ordering
Track events follow a strict sequence based on starting position logistics:
1. **By distance** - Shorter distances first (starter team moves counter-clockwise)
2. **Hurdles after flat** - Within same distance block, flat races before hurdles
3. **By age** - Youngest to oldest within each distance/hurdles block

This ordering minimizes equipment moves and starting position changes.

## Optimization Goals

These are soft goals, optimized in priority order. Later goals only improve if earlier goals are not compromised.

### Priority 1: Minimize Total Duration
Find the shortest possible schedule that satisfies all hard constraints.

### Priority 2: 10-Year-Olds Finish First
Rekrutt (J/G-Rekrutt) athletes should finish as early as possible. Young children have limited attention spans and parents want to leave early.

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

### Merging Tiers
- **10-year-olds (Rekrutt)**: Separate tier, can merge J/G-Rekrutt together
- **11-14 year-olds**: Can merge within this tier
- **15+ year-olds**: Can merge within this tier, with smart unmerging (see below)

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
Controlled by `USE_SECONDARY_VENUES` flag. When enabled, young athletes (J/G10) use secondary venues (e.g., shot put circle 2) which allows parallel scheduling.
