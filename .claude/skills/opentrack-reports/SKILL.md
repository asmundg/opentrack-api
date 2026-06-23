---
name: opentrack-reports
description: Generate the printable meet-day PDFs (start lists and field cards) for an OpenTrack competition. Use whenever the user wants start lists, field cards, heat sheets, lane sheets, or "the papers for the meet", mentions `opentrack reports`, or asks how to produce printouts from a competition slug/URL.
---

# OpenTrack meet-day reports

Two PDFs are produced straight from a competition's public OpenTrack data:

- **Start lists** (track events: heats, lanes, seed times):
  ```bash
  uv run opentrack reports start-lists <competition-url> [-d YYYY-MM-DD]
  ```
- **Field cards** (field events: throws/jumps attempt sheets):
  ```bash
  uv run opentrack reports field-cards <competition-url> [-d YYYY-MM-DD]
  ```

Run both from the repo root with `uv run` (it is a `uv` project; see the
`/python` skill). `start-lists` only emits track events and `field-cards` only
field events, so a full meet needs **both** commands.

## The source argument

`<competition-url>` is the public competition URL, the same one the `admin` and
`scheduler` commands take. A slug `bultf-ser5-26` is shorthand for:

```
https://norway.opentrack.run/x/2026/NOR/bultf-ser5-26/
```

The tool appends `/json/` and reads the public JSON (no token needed; it falls
back to a browser fetch if the host returns 403). A local `*.json` file path
works too.

Example:
```bash
uv run opentrack reports start-lists https://norway.opentrack.run/x/2026/NOR/bultf-ser5-26/
uv run opentrack reports field-cards https://norway.opentrack.run/x/2026/NOR/bultf-ser5-26/
```

## Options

| Flag | Meaning |
| --- | --- |
| `-d, --date YYYY-MM-DD` | Only that day's events (use for multi-day meets). |
| `-e, --event CODE` | Restrict to one event code; repeat for several (e.g. `-e 60H -e LJ`). |
| `--all-events` | Force every track (start-lists) / field (field-cards) event in the data. |
| `-o, --output FILE` | Output PDF path (auto-named if omitted). |

With no `-e`/`--all-events`, the relevant events found in the data are
processed. Both commands pre-validate every event in the dataset and fail loudly
on an unrecognized event code.

## Workflow

Generate the meet papers **after** the schedule, names, PB/SB and (for throws)
implement weights are synced to OpenTrack, so the PDFs carry final times, lanes
and seed marks. For a single day of a series, pass `-d` to keep each day's
printout separate.
