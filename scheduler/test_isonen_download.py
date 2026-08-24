import base64

import pytest

from scheduler.isonen_download import decode_export, parse_event_id

EVENT_ID = "cmmwiz8j709i9cq01r1y1y67s"


@pytest.mark.parametrize(
    "value",
    [
        EVENT_ID,
        f"https://isonen.no/event/{EVENT_ID}/",
        f"https://isonen.no/event/{EVENT_ID}",
        f"https://isonen.no/event/overview/?id={EVENT_ID}",
        f"https://isonen.no/event/participants/?tab=all&id={EVENT_ID}",
    ],
)
def test_parse_event_id_accepts_known_url_shapes(value):
    assert parse_event_id(value) == EVENT_ID


@pytest.mark.parametrize("value", ["", "https://isonen.no/", "overview", "12"])
def test_parse_event_id_rejects_junk(value):
    with pytest.raises(ValueError):
        parse_event_id(value)


def test_decode_export_returns_file_bytes():
    payload = {
        "data": {
            "exportParticipantList": {
                "status": True,
                "message": "file generated",
                "file": base64.b64encode(b"PK\x03\x04xlsx").decode(),
            }
        }
    }
    assert decode_export(payload) == b"PK\x03\x04xlsx"


def test_decode_export_raises_on_permission_error():
    payload = {
        "errors": [{"message": "Internal server error: Permission restricted"}],
        "data": None,
    }
    with pytest.raises(RuntimeError, match="Permission restricted"):
        decode_export(payload)


def test_decode_export_raises_on_failed_status():
    payload = {
        "data": {
            "exportParticipantList": {
                "status": False,
                "message": "no participants",
                "file": None,
            }
        }
    }
    with pytest.raises(RuntimeError, match="no participants"):
        decode_export(payload)
