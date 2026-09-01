"""Event-code translation between the admin schedule and OpenTrack's API."""

from .sync import _discipline_from_api_code, _to_api_event_code


def test_distance_codes_drop_the_metre_suffix():
    assert _to_api_event_code("400m") == "400"
    assert _to_api_event_code("60m") == "60"


def test_relay_codes_drop_the_metre_suffix_too():
    """OpenTrack lists the 4x60m relay as '4x60', same rule as a flat distance."""
    assert _to_api_event_code("4x60m") == "4x60"
    assert _to_api_event_code("4x100m") == "4x100"


def test_non_distance_codes_pass_through():
    for code in ("60H", "LJ", "SP", "PV"):
        assert _to_api_event_code(code) == code


def test_round_trips_back_to_the_schedule_code():
    for code in ("400m", "60m", "4x60m", "4x100m", "60H", "LJ"):
        assert _discipline_from_api_code(_to_api_event_code(code)) == code
