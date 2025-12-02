import json
import re
import urllib.error
import urllib.request
from typing import Any, Union


def fetch_json_data(url: str) -> dict[str, Any]:
    """Fetch JSON data from a given URL using only standard library."""
    if not url.endswith("/json/"):
        if url.endswith("/"):
            url += "json/"
        else:
            url += "/json/"

    print(f"Fetching data from {url}")
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as e:
        raise urllib.error.HTTPError(
            url, e.code, f"HTTP Error: {e.code} - {e.reason}", e.hdrs, e.fp
        )
    except urllib.error.URLError as e:
        raise urllib.error.URLError(f"URL Error: {e.reason}")
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"JSON Decode Error from {url}: {e.msg}", e.doc, e.pos
        )


def process_local_json(filepath: str) -> dict[str, Any]:
    """Process a local JSON file instead of fetching from URL."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {filepath}")
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"JSON Decode Error in {filepath}: {e.msg}", e.doc, e.pos
        )


def get_meeting_name(json_data: dict[str, Any]) -> str:
    """Extract meeting name from OpenTrack JSON data."""
    return json_data["fullName"]


def create_safe_filename(meeting_name: str) -> str:
    """Create a safe filename from the meeting name."""
    safe_name = re.sub(r"[^\w\s-]", "", meeting_name)
    safe_name = re.sub(r"[\s-]+", "_", safe_name)
    return safe_name


def clean_event_name(event_name: str) -> str:
    """Clean event name by removing category prefix if present."""
    # Strip category prefix from event name if present
    # For example, convert "G16 200 meter" to just "200 meter"
    event_name_parts = event_name.split(" ", 1)
    clean_name = event_name

    # Common Norwegian category prefixes: G (Gutter/Boys), J (Jenter/Girls),
    # K (Kvinner/Women), M (Menn/Men), followed by age group
    if len(event_name_parts) > 1:
        first_part = event_name_parts[0]
        # Check if first part starts with a category letter and contains numbers (age)
        if first_part.startswith(("G", "J", "K", "M")) and any(
            char.isdigit() for char in first_part
        ):
            clean_name = event_name_parts[1]

    return clean_name


# Define all known event codes centrally
TRACK_EVENT_CODES = [
    "60",
    "100",
    "200",
    "400",
    "600",
    "800",
    "1500",
    "3000",
    "5000",
    "10000",
    "60H",
    "80H",
    "100H",
    "110H",
    "200H",
    "300H",
    "400H",
    "3000SC",
    "4x100",
    "4x200",
    "4x400",
]

FIELD_EVENT_CODES = ["LJ", "TJ", "HJ", "DT", "JT", "SP", "HT", "PV", "BT"]

# Union of all known event codes
ALL_KNOWN_EVENT_CODES = TRACK_EVENT_CODES + FIELD_EVENT_CODES


def get_track_event_codes() -> list[str]:
    """Get list of all known track event codes."""
    return TRACK_EVENT_CODES.copy()


def get_field_event_codes() -> list[str]:
    """Get list of all known field event codes."""
    return FIELD_EVENT_CODES.copy()


def get_all_event_codes() -> list[str]:
    """Get list of all known event codes (track + field)."""
    return ALL_KNOWN_EVENT_CODES.copy()


def is_track_event(event_code: str) -> bool:
    """Check if an event code represents a track event."""
    return any(code in event_code for code in TRACK_EVENT_CODES)


def is_field_event(event_code: str) -> bool:
    """Check if an event code represents a field event."""
    return any(code in event_code for code in FIELD_EVENT_CODES)


def validate_events(
    data: dict[str, Any], strict_mode: bool = True
) -> list[dict[str, Any]]:
    """
    Validate that all events in the data are recognized.

    Args:
        data: JSON dictionary of competitor data from OpenTrack
        strict_mode: If True, raises exception for unrecognized events.
                    If False, just logs warnings and returns list of unrecognized events.

    Returns:
        List of unrecognized events (empty if all events are recognized)

    Raises:
        ValueError: If strict_mode is True and unrecognized events are found
    """
    if "events" not in data:
        if strict_mode:
            raise ValueError(
                "Data must be a dict with 'events' key from OpenTrack JSON"
            )
        return []

    unrecognized_events = []

    for event in data["events"]:
        event_code = event.get("eventCode", "")
        event_id = event.get("eventId", "unknown")
        event_name = event.get("name", "Unknown Event")

        # Check if this event matches any known event code
        is_recognized = any(code in event_code for code in ALL_KNOWN_EVENT_CODES)

        if not is_recognized:
            unrecognized_events.append(
                {
                    "eventCode": event_code,
                    "eventId": event_id,
                    "name": event_name,
                    "full_event": event,
                }
            )

    if unrecognized_events:
        error_details = []
        for event in unrecognized_events:
            error_details.append(
                f"  - {event['name']} (Code: '{event['eventCode']}', ID: {event['eventId']})"
            )

        error_message = (
            f"Found {len(unrecognized_events)} unrecognized event(s):\n"
            + "\n".join(error_details)
        )
        error_message += f"\n\nKnown track events: {', '.join(TRACK_EVENT_CODES)}"
        error_message += f"\nKnown field events: {', '.join(FIELD_EVENT_CODES)}"

        if strict_mode:
            raise ValueError(error_message)
        else:
            print(f"WARNING: {error_message}")

    return unrecognized_events


def load_opentrack_data(input_source: str) -> dict[str, Any]:
    """Load OpenTrack data from URL or local file."""
    if input_source.startswith("http://") or input_source.startswith("https://"):
        return fetch_json_data(input_source)
    else:
        return process_local_json(input_source)
