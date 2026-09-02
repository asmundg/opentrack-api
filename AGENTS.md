# Working agreement

How to work in this repo. Architecture and code layout live in `CLAUDE.md`; the
command pipeline lives in `README.md`.

## Start every session by syncing main

```bash
git fetch origin && git status -sb
```

If `main` is behind `origin/main`, pull before doing anything else.

This is not housekeeping. Work here lands as squash-merged PRs, so a stale local
`main` looks identical to a fixed bug being unfixed. A session once spent a
debugging cycle on OpenTrack's Cloudflare challenge that PR #4 had already
solved, because the fix was merged upstream and never pulled — the checkout was
still running the `playwright-stealth` code that commit deleted.

## Check you can push before planning any git work

The repo belongs to the `asmundg` GitHub account. A `GH_TOKEN` in the
environment overrides the credential helper, and if it names a different account
the push fails with a 403 after the work is already done:

```bash
gh api user -q .login    # must be asmundg
```

`direnv` sets the right token from the parent directory, but only for shells that
run direnv — agent tool calls generally do not. Read the token explicitly when
needed:

```bash
GH_TOKEN=$(env -u GH_TOKEN gh auth token --user asmundg) gh pr create ...
```

The same mismatch silently blocks anything else that resolves the repo by name.

## Branch fresh off origin/main

PRs are squash-merged, so a merged branch's commits keep SHAs that never appear
on `main`. Reusing one replays merged work into the next PR. Start each change
from `origin/main` and cherry-pick if the commits already exist elsewhere.

## Validate against the real pipeline

`from-events` is the authoritative gate for a schedule, and it stops at the first
violation. A change to scheduling, rendering, or sync is not done until a real
meet CSV still validates and renders — unit tests alone have missed bugs that
only appear with actual entries, such as an event vanishing from the rendered
grid.
