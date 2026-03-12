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
opentrack admin import-athletes https://norway.opentrack.run/en-gb/x/2026/NOR/bultf-ser2-26 ~/Downloads/Deltakerliste\ -\ Seriestevne\ 2.xlsx 
```

### Schedule

```bash
opentrack scheduler schedule ~/Downloads/Deltakerliste\ -\ Tromsølekene\ 2026\ -\ inne.xlsx --date 13.03.2026 --start-hour 19 --arena tromsohallen --max-duration 120
```

Make adjustments in schedule_events.csv, then recompute

```bash
opentrack scheduler from-events ~/Downloads/Deltakerliste\ -\ Seriestevne\ 2.csv schedule_events.csv --mix-genders
```

### Sync events

```bash
opentrack admin schedule https://norway.opentrack.run/en-gb/x/2026/NOR/bultf-ser2-26 schedule.csv
```

```bash
opentrack admin update-pbs https://norway.opentrack.run/en-gb/x/2026/NOR/bultf-ser2-26 schedule.csv
```
