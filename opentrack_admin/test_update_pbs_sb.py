"""Tests for update_pbs seeding both PB and SB onto competitor entries."""

from opentrack_admin import sync


class _FakeAPI:
    def __init__(self, competitors):
        self._competitors = competitors
        self.put_calls = []

    def get_competitors(self, comp_id, limit=500):
        return self._competitors

    def put_competitor(self, competitor):
        self.put_calls.append(competitor)


def _competitor():
    return {
        "competitor_id": "C1",
        "first_name": "Aurora",
        "last_name": "Molund Tangen",
        "category": "J17",
        "team_name": "IL i BUL Tromsø",
        "events_entered": [
            {"event_code": "100", "pb": None, "sb": None},
        ],
    }


def test_update_pbs_sets_pb_and_sb(monkeypatch):
    monkeypatch.setattr(
        sync, "lookup_athlete_pb_sb",
        lambda *a, **k: ("13.88", "14.03"),
    )
    api = _FakeAPI([_competitor()])

    updated, errors = sync.update_pbs(api, "comp1")

    assert errors == []
    assert updated == 1
    assert len(api.put_calls) == 1
    entry = api.put_calls[0]["events_entered"][0]
    assert entry["pb"] == "13.88"
    assert entry["sb"] == "14.03"


def test_update_pbs_sets_sb_even_when_pb_absent(monkeypatch):
    monkeypatch.setattr(
        sync, "lookup_athlete_pb_sb",
        lambda *a, **k: (None, "14.03"),
    )
    api = _FakeAPI([_competitor()])

    updated, errors = sync.update_pbs(api, "comp1")

    assert updated == 1
    entry = api.put_calls[0]["events_entered"][0]
    assert entry["pb"] is None
    assert entry["sb"] == "14.03"


def test_update_pbs_skips_put_when_nothing_changes(monkeypatch):
    monkeypatch.setattr(
        sync, "lookup_athlete_pb_sb",
        lambda *a, **k: (None, None),
    )
    api = _FakeAPI([_competitor()])

    updated, errors = sync.update_pbs(api, "comp1")

    assert updated == 0
    assert api.put_calls == []


def test_update_pbs_skips_put_when_values_already_current(monkeypatch):
    monkeypatch.setattr(
        sync, "lookup_athlete_pb_sb",
        lambda *a, **k: ("13.88", "14.03"),
    )
    comp = _competitor()
    comp["events_entered"][0]["pb"] = "13.88"
    comp["events_entered"][0]["sb"] = "14.03"
    api = _FakeAPI([comp])

    updated, errors = sync.update_pbs(api, "comp1")

    assert updated == 0
    assert api.put_calls == []
