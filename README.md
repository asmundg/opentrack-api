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

Idempotent: if a competition with the given slug already exists (looked up via
`{base}/x/{year}/NOR/{slug}/`), the create form is skipped and configuration
resumes from where it left off. Re-run the same command after a mid-flow
failure and it picks up from where it stopped.

```bash
opentrack admin import-athletes <opentrack url> <isonen xlsx>
```

### Schedule

```bash
opentrack scheduler schedule <isonen xlsx> --date <date> --start-hour <start> --arena <arena> --max-duration <duration>
```

If you do not have enough officials to run all field venues in parallel, declare
groups of event types that share officials/equipment with `--shared`. Each group
is comma-separated, and the flag can be repeated:

```bash
opentrack scheduler schedule <isonen xlsx> ... --shared jt,dt,ht --shared hj,lj
```

Events inside a shared group will be scheduled sequentially rather than in
parallel. The shared constraint is additive: a Lengde event with `--shared hj,lj`
still conflicts with a Tresteg event at the jumping pit *and* with a Høyde event
at the shared-officials bucket. The display still shows each event under its
natural venue. Pass the same `--shared` groups to `from-events` to keep the
constraint validator in sync.

If you also want to avoid impractical back-and-forth between event types at the
same venue (e.g. discus, hammer, discus, hammer at the throwing circle), add
`--sticky`:

```bash
opentrack scheduler schedule <isonen xlsx> ... --shared jt,dt,ht --sticky
```

`--sticky` makes events of the same type form a contiguous block per venue
(track is exempt; it has its own ordering rules). Pass the same flag to
`from-events` to validate manually edited schedules under the same rule. It is
a hard constraint, so very tight `--max-duration` budgets may become infeasible.

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
