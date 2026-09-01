"""Download the participant list XLSX straight from iSonen.

iSonen login goes through Idrettens ID (Google/Apple/passkey), which can't be
scripted, so we borrow the session from a Chrome you already logged in to. Start
it with a debugging port:

    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
        --remote-debugging-port=9222 --user-data-dir=~/Library/Application\\ Support/ChromeCDP

The "Last ned deltakerliste" dialog (Standard + Excel) is a single GraphQL query
returning the workbook base64-encoded, so we issue that query from a page on the
isonen.no origin instead of clicking through the UI.
"""

import base64
import binascii
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

DEFAULT_CDP_URL = "http://127.0.0.1:9222"

_EXPORT_QUERY = """query exportParticipantList($eventId: String!, $email: String!, $type: String, $includeDeregistered: Boolean) {
  exportParticipantList(
    where: {eventId: $eventId, email: $email, type: $type, includeDeregistered: $includeDeregistered}
  ) {
    status
    message
    file
  }
}"""

_FETCH_JS = """async ({query, eventId}) => {
  const response = await fetch("/api/graphql", {
    method: "POST",
    headers: {"content-type": "application/json"},
    credentials: "include",
    body: JSON.stringify({
      operationName: "exportParticipantList",
      variables: {eventId, email: "", type: "EXCEL", includeDeregistered: false},
      query,
    }),
  });
  return await response.json();
}"""

_EVENT_ID_RE = re.compile(r"^[a-z0-9]{20,}$")


def parse_event_id(event: str) -> str:
    """Extract the iSonen event id from an event URL, an overview URL, or a bare id."""
    candidate = event.strip()
    match = re.search(r"[?&]id=([a-z0-9]+)", candidate) or re.search(
        r"/event/([a-z0-9]+)", candidate
    )
    if match:
        candidate = match.group(1)
    if not _EVENT_ID_RE.match(candidate):
        raise ValueError(f"Not an iSonen event id or URL: {event!r}")
    return candidate


def decode_export(payload: dict[str, Any]) -> bytes:
    """Turn a GraphQL exportParticipantList response into workbook bytes."""
    for error in payload.get("errors") or []:
        raise RuntimeError(
            f"iSonen rejected the export: {error.get('message')}. "
            "Is the CDP Chrome logged in as an organiser for this event?"
        )
    export = (payload.get("data") or {}).get("exportParticipantList")
    if not export:
        raise RuntimeError(f"Unexpected iSonen response: {payload}")
    if not export.get("status"):
        raise RuntimeError(f"iSonen export failed: {export.get('message')}")
    try:
        return base64.b64decode(export["file"], validate=True)
    except (KeyError, binascii.Error) as exc:
        raise RuntimeError(f"iSonen returned an undecodable file: {exc}") from exc


def download_participant_xlsx(
    event: str, output: Path, cdp_url: str = DEFAULT_CDP_URL
) -> Path:
    """Fetch the standard participant list for `event` and write it to `output`."""
    event_id = parse_event_id(event)
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            raise RuntimeError(f"No browser context available at {cdp_url}")
        context = browser.contexts[0]
        page = next((p for p in context.pages if "isonen.no" in p.url), None)
        opened = page is None
        if page is None:
            page = context.new_page()
            page.goto("https://isonen.no/", wait_until="domcontentloaded")
        try:
            payload = page.evaluate(
                _FETCH_JS, {"query": _EXPORT_QUERY, "eventId": event_id}
            )
        finally:
            if opened:
                page.close()

    output.write_bytes(decode_export(payload))
    return output
