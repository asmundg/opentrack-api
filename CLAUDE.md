# CLAUDE.md - Track Meet Scheduler Architecture

This document describes the code layout and basic principles of the track meet scheduler system.

## Core Principles

### 1. All Interaction Through Top-Level CLI
- **Entry point**: `scheduler/cli.py`
- All user interaction goes through the CLI commands - no direct module imports for end users
- Commands are built using Typer for clean argument parsing and help text

### 2. Robust I/O with Pydantic Validation
- All CSV I/O goes through validated Pydantic DTOs (defined in `scheduler/dtos.py`)
- No opaque dictionaries in I/O boundaries
- Input validation happens at the boundary, not deep in business logic

### 3. Separation of Concerns
- **Parsing**: Converts external formats to internal models
- **Layout**: Merging and timing decided externally (by an agent/human) and expressed in the event CSV
- **Export**: Converts internal models to external formats
- **Validation**: Checks constraints without recomputation

## Code Layout

```
scheduler/
├── cli.py                      # Top-level CLI commands (MAIN ENTRY POINT)
├── __main__.py                 # Event grouping logic (group_events_by_type)
├── models.py                   # Internal data models (Event, EventGroup, Athlete)
├── types.py                    # Shared type definitions (SchedulingResult)
├── dtos.py                     # Pydantic DTOs for CSV I/O validation
│
├── isonen_parser.py            # Parse Isonen XLSX → Events & Athletes (one per category)
│
├── event_csv.py                # Event Overview CSV ↔ slot assignments
├── schedule_builder.py         # Event Overview CSV → SchedulingResult
├── constraint_validator.py     # Validate a manual/agent layout against the atoms
├── html_schedule_generator.py  # SchedulingResult → HTML grid
├── hurdle_plan_generator.py    # SchedulingResult → hurdle setup plan HTML
│
└── CONSTRAINTS.md              # Documentation of scheduling constraints
```

## Workflow

Layout (which categories merge, and each group's time and venue) is a
human/agent decision expressed in an event overview CSV. The CLI validates that
CSV and renders the outputs. There is no automatic solver.

```
Isonen XLSX + edited schedule_events.csv → from-events → HTML (+ hurdle plan)
```

**Command:**
```bash
scheduler from-events participants.xlsx schedule_events.csv -o schedule.html \
    --arena valhall --shared jt,dt,ht --shared hj,lj,tj
```

`from-events`:
1. Imports the event CSV (Pydantic-validated).
2. Validates all hard constraints (`constraint_validator.py`) and stops at the
   first violation with a specific message.
3. Builds a `SchedulingResult` from the manual times and renders the HTML grid
   and, when there are hurdle events, the hurdle setup plan.

To produce and iterate on `schedule_events.csv`, use the `track-meet-layout`
skill (`.claude/skills/`): it seeds a proposed merge/layout, detects mistakes in
batch (`layout_report.py`), and re-validates each revision with `from-events`
until every constraint passes.

## Data Flow

### Input: Isonen CSV
- Format: Participant registration data with events
- Fields: Name, Gender, Category, Club, Event, Date, Time, SB, PB
- Parsed by: `isonen_parser.py`
- Validated by: `AthleteScheduleRow` (Pydantic DTO)

### Internal: Event Grouping
- Individual events → EventGroups (merged categories)
- Logic in: `__main__.py:group_events_by_type()`
- Rules:
  - Track events: Max 8 athletes per group (one heat — hard lane cap)
  - Field events: Strong preference for ≥4 athletes per group; cap of 8 is a
    soft split target (oversized merged groups allowed with warning). See
    `scheduler/CONSTRAINTS.md` for the cross-tier merge rules
    (Masters↔15+, 11-14↔15-17).

### Processing: Layout & Validation
- Input: an event overview CSV (merges + start/end times) + Athletes
- `constraint_validator.py` checks coverage and all hard constraints against the
  raw `(event_type, category)` atoms, without re-deriving any grouping.
- `schedule_builder.py` turns the validated CSV into a `SchedulingResult`
  (immutable, frozen dataclass defined in `types.py`).

### Output: Multiple Formats

**HTML Schedule** (`html_schedule_generator.py`):
- Time × Venue grid with color-coded events
- Rowspan for multi-slot events
- Visual category grouping

**Hurdle plan** (`hurdle_plan_generator.py`):
- Per-heat hurdle setup (distance, height, lane/gutter layout) for hurdle events

**Event Overview CSV** (`event_csv.py`):
- One row per event group
- Fields: event_group_id, event_type, categories, venue, start_time, end_time, duration_minutes
- Validated by: `EventScheduleRow` (Pydantic DTO)
- Can be manually edited and re-imported

## Key Abstractions

### Event vs EventGroup
- **Event**: Single category of a single event type (e.g., "100m J15")
- **EventGroup**: Merged events that run together (e.g., "100m J15+J16")
  - Track groups: Athletes compete simultaneously in one heat
  - Field groups: Athletes share equipment, compete sequentially

### Slots vs Time
- Internally: Everything uses discrete "slots" (5-minute intervals)
- Externally: Converted to real times (HH:MM format)
- Base time: Configurable start hour/minute (default: 17:00)

### Constraints: Hard vs Soft
**Hard constraints** (must be satisfied):
- No venue conflicts (one event per venue per slot)
- No athlete conflicts (athlete can't compete in overlapping events)
- Track event ordering (by distance, then hurdles, then age)
- Event continuity (multi-slot events occupy consecutive slots)

**Soft goals** (the layout aims for; enforced by judgment and the skill's report, not a solver):
- Minimize total duration (compact makespan)
- Young athletes finish early
- Maximize recovery gaps for older athletes

## Validation Principles

### Input Validation (Pydantic DTOs)
- Happens at I/O boundaries
- Type checking, format validation, business rules
- Clear error messages with line numbers for CSV errors

### Constraint Validation (constraint_validator.py)
- Used when importing manually edited schedules
- Checks all hard constraints without recomputation
- Reports specific violations with event details

### No Opaque Dictionaries in I/O
- CSV rows → Pydantic models → Internal models
- Always validate at the boundary
- Type safety throughout

## Common Operations

### Adding a New CSV Output Format
1. Define Pydantic DTO in `dtos.py`
2. Create export function (SchedulingResult → CSV)
3. Add to CLI command in `cli.py`

### Adding a New Constraint
1. Implement the check in `constraint_validator.py`
2. Mirror it as a batch pre-check in the track-meet-layout skill's `layout_report.py` if useful
3. Document in `CONSTRAINTS.md`

### Modifying Event Grouping Rules
1. Update `__main__.py:group_events_by_type()`
2. Update tests if applicable

## Configuration

### Secondary Venues
- Controlled by: `--secondary-venues` flag
- Default: Enabled
- Effect: J/G10 athletes use separate shot put circle
- Global setting: `models.USE_SECONDARY_VENUES`

### Slot Duration
- Fixed: 5 minutes per slot
- Changing this requires updates to:
  - Event duration calculations
  - Output formatting
  - Manual CSV alignment validation

## Troubleshooting

### "Constraint violation detected"
- Check the error message for specific violation
- Common causes:
  - Event times don't align with 5-minute slots
  - Venue conflicts (overlapping events at same venue)
  - Athlete conflicts (athlete in two places at once)
  - Track ordering violated (distance order or age order)

### "Constraint violation" won't clear
- The layout is over-constrained or mis-merged. `from-events` reports one
  violation at a time; the skill's `layout_report.py --xlsx` lists all athlete
  conflicts, age-merge and spacing problems at once.
- Try: re-split an oversized or illegal merge, move a row to a free slot, enable
  secondary venues, or widen the track/field reconfiguration gaps.

### CSV Import Errors
- Pydantic validation will show line number and specific error
- Common issues:
  - Invalid time format (must be HH:MM)
  - Missing required columns
  - Incorrect enum values (event types, venues, categories)

## Future Extensions

The architecture supports:
- Alternative layout generators (e.g. an optimizer that emits the same event CSV)
- Additional output formats (PDF, API, etc.)
- Web UI (CLI logic remains unchanged)
- Custom constraint plugins
- Multi-day scheduling (extend slot calculation)

All extensions should maintain the core principle: **All user interaction through top-level CLI**.
