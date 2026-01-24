# OpenTrack XLSX Event Export

This tool converts Isonen CSV participant data to OpenTrack XLSX format for bulk event creation.

## Quick Start

```bash
# Export events from Isonen CSV to OpenTrack XLSX
uv run python -m scheduler.cli to-opentrack-xlsx participants.csv \
  -o opentrack_events.xlsx \
  --meet-name "Seriestevne 9-2025"
```

## What It Does

1. **Reads Isonen CSV**: Parses the participant registration data
2. **Extracts Events**: Identifies all unique category + event combinations
3. **Collapses Categories**: Merges age categories ≤10 into "10"
4. **Exports to XLSX**: Creates an Excel file ready for OpenTrack upload

## Category Collapsing Logic

To match OpenTrack's event structure, all categories aged 10 and under are collapsed to "10":

| Original Category | Exported Category |
|------------------|-------------------|
| Gutter 9 | Gutter 10 |
| Gutter Rekrutt 6-8 | Gutter 10 |
| Jenter 9 | Jenter 10 |
| Jenter Rekrutt 6-8 | Jenter 10 |
| Gutter 11+ | _(unchanged)_ |
| Jenter 11+ | _(unchanged)_ |

**Rationale**: In OpenTrack, younger age groups (6-8 rekrutt, 9, and 10) all compete together in the "10" category.

## Input Format

The tool expects an Isonen-format CSV with these columns:

```csv
Fornavn,Etternavn,Kjønn,Klasse,Klubb,Øvelse,Dato,Kl.,SB,PB
```

**Required columns**:
- `Klasse` - Age category (e.g., "Gutter 15", "Jenter Rekrutt 6-8")
- `Øvelse` - Event name (e.g., "100 meter", "Lengde", "Kule")

See `example_isonen_input.csv` for a complete example.

## Output Format

The XLSX file contains two columns:

| Category | Event |
|----------|-------|
| Gutter 10 | 60 meter |
| Gutter 10 | Kule |
| Gutter 15 | 100 meter |
| Jenter 15 | Lengde |

**Key features**:
- ✅ Sorted alphabetically for easy review
- ✅ Duplicates automatically removed
- ✅ Formatted headers and auto-sized columns
- ✅ Ready to upload to OpenTrack

## Example Workflow

```bash
# 1. Export events from Isonen CSV
uv run python -m scheduler.cli to-opentrack-xlsx \
  ser9_participants.csv \
  -o ser9_events.xlsx

# Output:
# ✅ Exported 20 unique events to OpenTrack XLSX format
#    File saved to: /path/to/ser9_events.xlsx
#
# 💡 Note: Categories <=10 have been collapsed to '10'

# 2. Upload ser9_events.xlsx to OpenTrack
#    - Log in to OpenTrack admin
#    - Navigate to competition events
#    - Use bulk import feature to upload the XLSX file

# 3. (Optional) Generate the full schedule
uv run python -m scheduler.cli schedule \
  ser9_participants.csv \
  -o schedule.html
```

## CLI Options

```
uv run python -m scheduler.cli to-opentrack-xlsx --help

Options:
  -o, --output PATH       Output XLSX file path [default: opentrack_events.xlsx]
  --meet-name TEXT        Name of the track meet [default: "Track Meet"]
  -q, --quiet             Suppress detailed output
  --help                  Show this message and exit
```

## Testing

An example input file is provided to test the export:

```bash
uv run python -m scheduler.cli to-opentrack-xlsx \
  example_isonen_input.csv \
  -o test_output.xlsx
```

Expected output: 20 unique events with proper category collapsing.

## Troubleshooting

### "No valid events found"
- Check that your CSV has the required columns: `Klasse` and `Øvelse`
- Verify the CSV is UTF-8 encoded
- Ensure there are no empty rows at the top of the file

### "Categories not collapsing correctly"
The collapsing logic looks for:
- Category names containing "Rekrutt"
- Category names matching "Gutter 9" or "Jenter 9"
- Numeric ages ≤10

If using different category naming conventions, the `collapse_category()` function in `scheduler/opentrack_xlsx_exporter.py` may need adjustment.

## Implementation Details

**Module**: `scheduler/opentrack_xlsx_exporter.py`

**Key functions**:
- `collapse_category(category: str) -> str` - Applies category collapsing logic
- `extract_events_from_isonen_csv(csv_path: Path) -> list[EventRow]` - Parses CSV and deduplicates events
- `export_to_opentrack_xlsx(events: list[EventRow], output_path: Path)` - Creates formatted Excel file

**Dependencies**:
- `openpyxl>=3.1.0` - Excel file generation
- Standard library: `csv`, `pathlib`, `typing`

## Related Commands

```bash
# View participant info without scheduling
uv run python -m scheduler.cli info participants.csv

# Generate full automated schedule
uv run python -m scheduler.cli schedule participants.csv -o schedule.html

# Manual scheduling workflow
uv run python -m scheduler.cli schedule participants.csv
# ... manually edit schedule_events.csv ...
uv run python -m scheduler.cli from-events participants.csv schedule_events.csv
```

See `CLAUDE.md` for complete scheduler architecture documentation.
