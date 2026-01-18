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
- **Scheduling**: Pure constraint solving logic
- **Export**: Converts internal models to external formats
- **Validation**: Checks constraints without recomputation

## Code Layout

```
scheduler/
├── cli.py                      # Top-level CLI commands (MAIN ENTRY POINT)
├── __main__.py                 # Event grouping logic
├── models.py                   # Internal data models (Event, EventGroup, Athlete)
├── types.py                    # Shared type definitions (SchedulingResult)
├── dtos.py                     # Pydantic DTOs for CSV I/O validation
│
├── isonen_parser.py           # Parse Isonen CSV → Events & Athletes
├── functional_scheduler.py    # Core constraint solver (Z3)
│
├── html_schedule_generator.py # SchedulingResult → HTML
├── csv_exporter.py            # SchedulingResult → Athlete CSV
├── event_csv.py               # SchedulingResult ↔ Event Overview CSV
├── schedule_builder.py        # Event Overview CSV → SchedulingResult
├── constraint_validator.py    # Validate manual schedules
│
└── CONSTRAINTS.md             # Documentation of scheduling constraints
```

## Workflow Options

### Option 1: Fully Automated
```
Isonen CSV → schedule command → HTML + Athlete CSV + Event CSV
```

**Command:**
```bash
scheduler schedule participants.csv -o schedule.html
```

**Outputs:**
- `schedule.html` - Visual schedule grid (time × venue)
- `schedule.csv` - Updated participant list with start times
- `schedule_events.csv` - Event overview with start/end times

### Option 2: Manual Adjustment Workflow
```
1. Isonen CSV → schedule command → Event CSV
2. Manually edit Event CSV (adjust event times)
3. Event CSV → from-events command → HTML + Athlete CSV
```

**Commands:**
```bash
# Step 1: Generate initial schedule
scheduler schedule participants.csv -o schedule.html

# Step 2: Manually edit schedule_events.csv

# Step 3: Regenerate outputs from manual schedule
scheduler from-events participants.csv schedule_events.csv -o final_schedule.html
```

This workflow allows for:
- Initial automated optimization
- Manual adjustments for special circumstances
- Validation that manual changes satisfy all constraints
- Final output generation

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
  - Track events: Max 8 athletes per group (one heat)
  - Field events: 3-8 athletes per group (equipment sharing)

### Processing: Constraint Solving
- Input: EventGroups + Athletes + Configuration
- Solver: Z3 SAT solver with multi-phase optimization
- Output: SchedulingResult (immutable, frozen dataclass)
- Logic in: `functional_scheduler.py`

### Output: Multiple Formats

**HTML Schedule** (`html_schedule_generator.py`):
- Time × Venue grid with color-coded events
- Rowspan for multi-slot events
- Visual category grouping

**Athlete CSV** (`csv_exporter.py`):
- Updated Isonen CSV with computed start times
- Preserves all original columns
- Updates "Kl." and "Dato" fields

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

**Soft constraints** (optimization objectives):
- Minimize total duration (Phase 1)
- Young athletes finish early (Phase 2)
- Maximize recovery gaps for older athletes (Phase 3)

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
1. Implement constraint in `functional_scheduler.py`
2. Add validation logic in `constraint_validator.py`
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

### Solver Timeouts
- Default: 10 seconds per optimization phase
- Configurable via: `--timeout` flag
- Increase for larger meets or more complex constraints

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

### "No solution found"
- Schedule is over-constrained
- Try:
  - Increase max duration
  - Add more personnel
  - Enable secondary venues
  - Adjust track spacing constraints

### CSV Import Errors
- Pydantic validation will show line number and specific error
- Common issues:
  - Invalid time format (must be HH:MM)
  - Missing required columns
  - Incorrect enum values (event types, venues, categories)

## Future Extensions

The architecture supports:
- Multiple scheduling algorithms (plug in alternative to Z3)
- Additional output formats (PDF, API, etc.)
- Web UI (CLI logic remains unchanged)
- Custom constraint plugins
- Multi-day scheduling (extend slot calculation)

All extensions should maintain the core principle: **All user interaction through top-level CLI**.
