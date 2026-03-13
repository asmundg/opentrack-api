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

### Create Competition

```bash
opentrack admin create "Seriestevne 2" "bultf-ser2-26" 2026-02-23 bultromsofriidrett@gmail.com BULTF --website https://bul-tromso.no/bul-troms%C3%B8/friidrett --entry-link https://isonen.no/event/cmjszsar000are3010ml8gvrc/
```

```bash
opentrack admin import-athletes <opentrack url> <isonen xlsx>
```

### Schedule

```bash
opentrack scheduler schedule <isonen xlsx> --date <date> --start-hour <start> --arena <arena> --max-duration <duration>
```

Make adjustments in schedule_events.csv, then recompute

```bash
opentrack scheduler from-events <schedule_events.csv> --mix-genders
```

### Sync events

```bash
opentrack admin schedule <opentrack-url> schedule.csv
```

```bash
opentrack admin update-pbs <opentrack-url> schedule.csv
```

### Reports

```bash
opentrack reports competitors-by-club <opentrack-url>
```
