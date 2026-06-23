"""Browser-free meet maintenance built on the OpenTrack REST API.

Covers the parts of the workflow a director-level API token can do:

* setting event start times / day / field attempts (``set_event_times``)
* seeding competitor PB data (``update_pbs``)

Creating competitions, importing athletes and merging events are not available
to a director token (the API rejects the relevant POSTs), so those stay on the
Playwright path.
"""

import logging
import re

from pblookup.lookup import PBLookupService

from .api import OpenTrackAPI, OpenTrackAPIError
from .events import (
    AttemptConfig,
    EventMergeGroup,
    EventSchedule,
    fold_masters_to_senior,
    get_category_age,
    is_horizontal_field_event,
    lookup_athlete_pb_sb,
)

logger = logging.getLogger(__name__)


def _to_api_event_code(schedule_code: str) -> str:
    """Map an admin discipline code to OpenTrack's API ``event_code``.

    Distances carry an 'm' in the schedule ("400m") but are bare in the API
    ("400"); hurdles ("60H") and field codes ("LJ") already match.
    """
    m = re.match(r"^(\d+)m$", schedule_code)
    return m.group(1) if m else schedule_code


def _discipline_from_api_code(api_code: str) -> str:
    """Inverse of :func:`_to_api_event_code`: API ``event_code`` to admin code."""
    return f"{api_code}m" if api_code.isdigit() else api_code


def set_merged_names(
    api: OpenTrackAPI,
    comp_id: str,
    merge_groups: list[EventMergeGroup],
) -> tuple[int, list[tuple[str, str]]]:
    """Set each merged track event's combined name on its primary, via the API.

    Merging itself needs the browser, but the merged event's display name (e.g.
    ``"G/J 11-13 60 meter hekk"``) is just the primary event's ``name`` field, so
    it can be PATCHed over the API. Running this on the API path keeps names in
    sync even when the browser merge phase is skipped (``--no-merge``) or when a
    prior merge left the primary with its single-category name.

    Each group's primary is matched to its OpenTrack event by ``(event_code,
    category)``. Idempotent: a primary already carrying the combined name is left
    untouched. Returns ``(updated, errors)``.
    """
    events = api.get_events(comp_id)
    by_key: dict[tuple[str, str], dict] = {
        (str(e["event_code"]), str(e["category"])): e for e in events
    }

    updated = 0
    errors: list[tuple[str, str]] = []
    for group in merge_groups:
        primary = group.primary
        label = group.merged_name
        key = (_to_api_event_code(primary.event), primary.search_category)
        event = by_key.get(key)
        if event is None:
            errors.append((label, "no matching OpenTrack event"))
            logger.warning("No OpenTrack event for merged group %s (looked up %s)", label, key)
            continue

        if event.get("name") == group.merged_name:
            continue

        try:
            api.patch_event(event, name=group.merged_name)
            updated += 1
            logger.info("Named %s (%s) -> %s", event["event_id"], key, group.merged_name)
        except OpenTrackAPIError as e:
            errors.append((label, str(e)))

    return updated, errors


def set_event_times(
    api: OpenTrackAPI,
    comp_id: str,
    schedules: list[EventSchedule],
    day: int | None = None,
) -> tuple[int, list[tuple[str, str]]]:
    """Set start time (and, for horizontal field events, attempts) per event.

    Matches each schedule row to its OpenTrack event by ``(event_code,
    category)``, then PATCHes ``r1_time`` (and ``day`` when given). Horizontal
    field events also get ``max_field_attempts`` and ``cut_after_round`` from the
    category's :class:`AttemptConfig`.

    Returns ``(updated, errors)`` where ``errors`` is ``(label, message)``.
    """
    events = api.get_events(comp_id)
    by_key: dict[tuple[str, str], dict] = {
        (str(e["event_code"]), str(e["category"])): e for e in events
    }

    updated = 0
    errors: list[tuple[str, str]] = []
    for sched in schedules:
        label = f"{sched.category} {sched.event}"
        if sched.category.upper() == "FIFA":
            continue

        key = (_to_api_event_code(sched.event), fold_masters_to_senior(sched.category))
        event = by_key.get(key)
        if event is None:
            errors.append((label, "no matching OpenTrack event"))
            logger.warning("No OpenTrack event for %s (looked up %s)", label, key)
            continue

        fields: dict[str, object] = {"r1_time": sched.start_time.strftime("%H:%M")}
        if day is not None:
            fields["day"] = day
        if is_horizontal_field_event(sched.event):
            cfg = AttemptConfig.for_category(sched.category)
            fields["max_field_attempts"] = cfg.attempts
            fields["cut_after_round"] = cfg.field_cut

        try:
            api.patch_event(event, **fields)
            updated += 1
            logger.info("Set %s (%s) -> %s", event["event_id"], label, fields["r1_time"])
        except OpenTrackAPIError as e:
            errors.append((label, str(e)))

    return updated, errors


def update_pbs(
    api: OpenTrackAPI,
    comp_id: str,
    default_club: str = "",
    debug: bool = False,
    event_filter: str | None = None,
    category_filter: str | None = None,
) -> tuple[int, list[tuple[str, str]]]:
    """Seed competitor PB and SB values from the external stats site.

    Competitor-driven: every entered event is read straight from the
    competitors endpoint, so this works before seeding and across merged/renamed
    events. For each event the athlete's all-time personal best (``pb``) and
    current-season best (``sb``) are looked up in a single matched pass.
    Athletes under 13 are skipped. Only competitors whose ``pb``/``sb`` data
    actually changes are PUT back.

    Optional ``event_filter`` (admin discipline code, e.g. ``"LJ"``) and
    ``category_filter`` (e.g. ``"J15"``) restrict the update to a single event.

    Returns ``(competitors_updated, errors)``.
    """
    competitors = api.get_competitors(comp_id)
    service = PBLookupService(debug=debug)

    api_event_filter = _to_api_event_code(event_filter) if event_filter else None
    cat_filter = fold_masters_to_senior(category_filter) if category_filter else None

    updated = 0
    errors: list[tuple[str, str]] = []
    for comp in competitors:
        name = f"{comp.get('first_name', '')} {comp.get('last_name', '')}".strip()
        category = comp.get("category") or ""

        if cat_filter and fold_masters_to_senior(category) != cat_filter:
            continue

        age = get_category_age(category)
        if age is not None and age < 13:
            continue

        club = comp.get("team_name") or default_club
        changed = False
        for entry in comp.get("events_entered", []):
            api_code = str(entry.get("event_code") or "")
            if api_event_filter and api_code != api_event_filter:
                continue

            discipline = _discipline_from_api_code(api_code)
            pb_value, sb_value = lookup_athlete_pb_sb(
                service, name, club, "", discipline, category, debug=debug
            )
            if pb_value is not None and entry.get("pb") != pb_value:
                entry["pb"] = pb_value
                changed = True
            if sb_value is not None and entry.get("sb") != sb_value:
                entry["sb"] = sb_value
                changed = True

        if not changed:
            continue

        try:
            api.put_competitor(comp)
            updated += 1
            logger.info("Updated PBs for %s (%s)", comp.get("competitor_id"), name)
        except OpenTrackAPIError as e:
            errors.append((name, str(e)))

    return updated, errors
