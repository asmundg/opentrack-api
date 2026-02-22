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
uv run python main.py admin create "Seriestevne 2" "bultf-ser2-26" 2026-02-23 bultromsofriidrett@gmail.com BULTF --website https://bul-tromso.no/bul-troms%C3%B8/friidrett --entry-link https://isonen.no/event/cmjszsar000are3010ml8gvrc/
```

```bash
uv run python main.py admin import-athletes https://norway.opentrack.run/en-gb/x/2026/NOR/bultf-ser2-26 ~/Downloads/Deltakerliste\ -\ Seriestevne\ 2.xlsx 
```

Make adjustments in schedule_events.csv, then recompute

```bash
uv run opentrack scheduler from-events ~/Downloads/Deltakerliste\ -\ Seriestevne\ 2.csv schedule_events.csv --mix-genders
```
