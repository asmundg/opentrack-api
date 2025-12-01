# OpenTrack Admin Automation

Playwright-based automation for administering [OpenTrack](https://norway.opentrack.run) events.

Since OpenTrack doesn't provide an API, this tool uses browser automation to perform administrative tasks like creating competitions, managing entries, etc.

## Setup

```bash
# Install dependencies
uv sync

# Install Playwright browsers
uv run playwright install chromium

# Copy and configure environment
cp .env.example .env
# Edit .env with your OpenTrack credentials
```

## Quick Start: Recording Workflows

The fastest way to build automation is to record your interactions:

```bash
# Launch the recorder - it will open a browser
uv run playwright codegen https://norway.opentrack.run

# Or use the CLI helper
uv run python -m opentrack_admin.cli record
```

This opens a browser where you can:
1. Log in to OpenTrack
2. Navigate through creating a competition
3. Watch as Playwright generates Python code for each click/input

The generated code shows you the exact selectors and steps needed, which you can then copy into `opentrack_admin/competition.py`.

## Usage

### Test Login

```bash
uv run python -m opentrack_admin.cli test-login
```

### Create Competition (once flow is recorded)

```bash
uv run python -m opentrack_admin.cli create "My Competition Name" 2025-06-15 \
    --venue "Bislett Stadium" \
    --city "Oslo"
```

## Project Structure

```
opentrack_admin/
├── __init__.py
├── browser.py      # Browser/session management
├── cli.py          # Command-line interface
├── competition.py  # Competition creation logic (update after recording)
└── config.py       # Configuration from environment
```

## Development Workflow

1. **Record the flow**: Run `uv run playwright codegen https://norway.opentrack.run`
2. **Copy selectors**: Take the generated Python code and update `competition.py`
3. **Test**: Run the automation in headed mode (`OPENTRACK_HEADLESS=false`)
4. **Refine**: Add error handling, waits, and retries as needed

## Tips for Robust Automation

- Use `page.wait_for_load_state("networkidle")` after navigation
- Prefer text-based selectors (`text=Submit`) over CSS when stable
- Use `page.locator()` with `.wait_for()` for dynamic content
- Set `OPENTRACK_SLOW_MO=100` to slow down for debugging

# Claude screenshot converter

I have a Norwegian athletics competition timetable image. Please extract the event schedule and create a CSV with three columns: category, event, start_time.
Requirements:

Expand all slash-separated categories (like G16/G17/J15) into individual rows, one per category
Use standard event codes: 60m (for 60m sprint), LJ (long jump), HJ (high jump), SP (shot put), TJ (triple jump)
Use 24-hour time format (HH:MM) for start times
Include all events from the schedule"
