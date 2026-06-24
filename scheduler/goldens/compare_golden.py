#!/usr/bin/env python3
"""Golden evaluation harness for the track-meet-layout skill.

Two subcommands:

  export   golden-sched JSON -> schedule_events.csv (the golden timetable as a
           CSV the validator can ingest). Used to confirm the golden itself is
           valid under our constraints and to establish meet flags.

  compare  produced schedule_events.csv  vs  golden-sched JSON -> divergence
           report (coverage, makespan, per-atom start delta, merge F1, order).

Run from repo root with `uv run python <thisfile> ...`.
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

# golden eventCode -> EventType.value (Norwegian, matches schedule_events.csv)
CODE2TYPE = {
    "60": "60m", "100": "100m", "150": "150m", "200": "200m", "300": "300m",
    "400": "400m", "600": "600m", "800": "800m", "1500": "1500m",
    "3000": "3000m", "5000": "5000m",
    "60H": "60m hekk", "80H": "80m hekk", "100H": "100m hekk", "200H": "200m hekk",
    "SP": "Kule", "LJ": "Lengde", "TJ": "Tresteg", "HJ": "Høyde",
    "DT": "Diskos", "JT": "Spyd", "HT": "Slegge", "BT": "Liten ball",
    "PV": "Stavsprang",
}

# golden category -> Category.value
CAT_MAP = {"G10": "G-Rekrutt", "J10": "J-Rekrutt",
           "MS": "Menn Senior", "KS": "Kvinner Senior"}

# event_type.value -> default venue string (matches dump_groups output)
VENUE = {
    "Kule": "shot_put_circle", "Høyde": "high_jump_area",
    "Lengde": "jumping_pit", "Tresteg": "jumping_pit",
    "Diskos": "throwing_circle", "Slegge": "throwing_circle",
    "Spyd": "javelin_area", "Liten ball": "javelin_area",
    "Stavsprang": "pole_vault_area",
}
TRACK_TYPES = {"60m", "100m", "150m", "200m", "300m", "400m", "600m", "800m",
               "1500m", "3000m", "5000m", "60m hekk", "80m hekk",
               "100m hekk", "200m hekk"}


def _venue_of(etype: str) -> str:
    return "track" if etype in TRACK_TYPES else VENUE[etype]


def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _from_min(mins: int) -> str:
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _cat(c: str) -> str:
    return CAT_MAP.get(c, c)


def load_golden(path: Path):
    """Return list of atoms: (etype_value, category_value, start_min, group_key)."""
    d = json.loads(path.read_text())
    atoms = []
    for e in d["events"]:
        code = e["eventCode"]
        if code not in CODE2TYPE:
            raise SystemExit(f"Unknown golden eventCode {code!r} in {path.name}")
        etype = CODE2TYPE[code]
        cat = _cat(e["category"])
        t = e.get("r1Time")
        if not t:
            raise SystemExit(f"Event {e['name']!r} has no r1Time in {path.name}")
        start = _to_min(t)
        # merge group = atoms sharing (eventCode, time): they run together
        gkey = (code, t)
        atoms.append((etype, cat, start, gkey))
    return atoms, d


def load_produced(path: Path):
    """Return list of atoms from a schedule_events.csv produced by the skill."""
    atoms = []
    with path.open(encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            etype = row["event_type"].strip()
            start = _to_min(row["start_time"].strip())
            gkey = ("row", i)  # each CSV row is one merge group
            for cat in row["categories"].split(","):
                atoms.append((etype, cat.strip(), start, gkey))
    return atoms


def cmd_export(args):
    atoms, d = load_golden(Path(args.golden))
    # group atoms by gkey -> one CSV row each
    groups = defaultdict(list)
    order = []
    for etype, cat, start, gkey in atoms:
        if gkey not in groups:
            order.append(gkey)
        groups[gkey].append((etype, cat, start))
    rows = []
    for gkey in order:
        members = groups[gkey]
        etype = members[0][0]
        start = members[0][2]
        cats = ",".join(sorted({c for _, c, _ in members}))
        rows.append({
            "event_group_id": f"{etype}_{cats}_golden",
            "event_type": etype,
            "categories": cats,
            "venue": _venue_of(etype),
            "start_time": _from_min(start),
            "end_time": _from_min(start + 5),  # placeholder; validator recomputes
        })
    out = Path(args.output)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["event_group_id", "event_type",
                                          "categories", "venue", "start_time",
                                          "end_time"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} golden rows -> {out}")


def _merge_pairs(atoms):
    """Set of unordered atom-id pairs that are in the same merge group,
    restricted to same event_type (cross-type pairs are never 'merged')."""
    by_group = defaultdict(list)
    ids = {}
    for etype, cat, start, gkey in atoms:
        aid = (etype, cat)
        ids[aid] = True
        by_group[gkey].append(aid)
    pairs = set()
    for members in by_group.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if a[0] == b[0]:  # same event_type
                    pairs.add(frozenset((a, b)))
    return pairs, set(ids)


def cmd_compare(args):
    g_atoms, d = load_golden(Path(args.golden))
    p_atoms = load_produced(Path(args.produced))

    g_ids = {(e, c): s for e, c, s, _ in g_atoms}
    p_ids = {(e, c): s for e, c, s, _ in p_atoms}

    name = d.get("fullName", Path(args.golden).stem)
    print(f"=== {name}  ({args.produced}) ===")

    # 1. coverage
    missing = sorted(set(g_ids) - set(p_ids))
    extra = sorted(set(p_ids) - set(g_ids))
    print(f"atoms: golden={len(g_ids)} produced={len(p_ids)} "
          f"missing={len(missing)} extra={len(extra)}")
    if missing:
        print("  MISSING:", ", ".join(f"{e}/{c}" for e, c in missing))
    if extra:
        print("  EXTRA:  ", ", ".join(f"{e}/{c}" for e, c in extra))

    # 2. makespan (span of start times)
    g_starts = list(g_ids.values())
    p_starts = list(p_ids.values())
    g_span = max(g_starts) - min(g_starts)
    p_span = max(p_starts) - min(p_starts)
    print(f"start span: golden={g_span}min ({_from_min(min(g_starts))}-"
          f"{_from_min(max(g_starts))})  produced={p_span}min "
          f"({_from_min(min(p_starts))}-{_from_min(max(p_starts))})  "
          f"delta={p_span - g_span:+d}min")

    # 3. per-atom start delta (relative to each schedule's own first start,
    #    so we compare shape, not absolute clock which both anchor at 17:00)
    g0, p0 = min(g_starts), min(p_starts)
    common = sorted(set(g_ids) & set(p_ids))
    deltas = []
    for k in common:
        deltas.append((p_ids[k] - p0) - (g_ids[k] - g0))
    if deltas:
        ad = [abs(x) for x in deltas]
        ad.sort()
        mean = sum(ad) / len(ad)
        median = ad[len(ad) // 2]
        within = {
            "<=5": sum(1 for x in ad if x <= 5),
            "<=15": sum(1 for x in ad if x <= 15),
            "<=30": sum(1 for x in ad if x <= 30),
        }
        print(f"per-atom |start delta| (vs own first start): "
              f"mean={mean:.1f} median={median} max={max(ad)}  "
              f"within 5/15/30min = {within['<=5']}/{within['<=15']}/"
              f"{within['<=30']} of {len(ad)}")

    # 4. merge agreement (F1 on same-type merged pairs)
    gp, _ = _merge_pairs(g_atoms)
    pp, _ = _merge_pairs(p_atoms)
    # restrict to atoms present on both sides
    both = set(g_ids) & set(p_ids)
    gp = {pr for pr in gp if all(a in both for a in pr)}
    pp = {pr for pr in pp if all(a in both for a in pr)}
    tp = len(gp & pp)
    prec = tp / len(pp) if pp else 1.0
    rec = tp / len(gp) if gp else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    print(f"merge pairs: golden={len(gp)} produced={len(pp)} agree={tp}  "
          f"precision={prec:.2f} recall={rec:.2f} F1={f1:.2f}")
    if args.verbose:
        only_g = gp - pp
        only_p = pp - gp
        if only_g:
            print("  golden-merged, produced-split:",
                  ", ".join("+".join(sorted(c for _, c in pr)) +
                            f"({next(iter(pr))[0]})" for pr in list(only_g)[:20]))
        if only_p:
            print("  produced-merged, golden-split:",
                  ", ".join("+".join(sorted(c for _, c in pr)) +
                            f"({next(iter(pr))[0]})" for pr in list(only_p)[:20]))

    if args.json_out:
        summary = {
            "name": name, "golden_atoms": len(g_ids),
            "produced_atoms": len(p_ids), "missing": len(missing),
            "extra": len(extra), "golden_span": g_span, "produced_span": p_span,
            "span_delta": p_span - g_span,
            "start_delta_mean": (sum(abs(x) for x in deltas) / len(deltas))
            if deltas else None,
            "merge_f1": round(f1, 3), "merge_precision": round(prec, 3),
            "merge_recall": round(rec, 3),
        }
        Path(args.json_out).write_text(json.dumps(summary, indent=2))
    return f1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="golden JSON -> schedule_events.csv")
    ex.add_argument("golden")
    ex.add_argument("-o", "--output", required=True)
    ex.set_defaults(func=cmd_export)

    cp = sub.add_parser("compare", help="produced CSV vs golden JSON")
    cp.add_argument("produced")
    cp.add_argument("golden")
    cp.add_argument("-v", "--verbose", action="store_true")
    cp.add_argument("--json-out")
    cp.set_defaults(func=cmd_compare)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
