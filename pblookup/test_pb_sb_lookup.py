"""Tests for PB + SB lookup.

The stats site renders all-time personal records (PR) and current-season bests
(SB) with the same table layout under different request "views". These tests
cover (1) the scraper selecting the right view, (2) parsing season bests from a
real saved SB page, and (3) lookup_pb_sb matching the athlete once and returning
both performances.
"""

from pathlib import Path

from pblookup.lookup import PBLookupService
from pblookup.models import Athlete, Result, SearchCandidate
from pblookup.scraper import MinfriidrettsScraper

FIXTURES = Path(__file__).parent / "fixtures"


# --- scraper view selection -------------------------------------------------

class _FakeResponse:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        pass


class _RecordingSession:
    """Captures the GET/POST the scraper issues for a profile view."""

    def __init__(self, text):
        self._text = text
        self.get_calls = []
        self.post_calls = []
        self.headers = {}

    def get(self, url, timeout=None):
        self.get_calls.append(url)
        return _FakeResponse(self._text)

    def post(self, url, data=None, timeout=None):
        self.post_calls.append((url, data))
        return _FakeResponse(self._text)


def test_pr_view_uses_get_showathlete():
    scraper = MinfriidrettsScraper()
    scraper.session = _RecordingSession((FIXTURES / "profile_pr.html").read_text())

    scraper.fetch_athlete_profile(48787)  # default view = PR

    assert scraper.session.post_calls == []
    assert any("showathlete=48787" in url for url in scraper.session.get_calls)


def test_sb_view_uses_post_type_sb():
    scraper = MinfriidrettsScraper()
    scraper.session = _RecordingSession((FIXTURES / "profile_sb.html").read_text())

    scraper.fetch_athlete_profile(48787, view="SB")

    assert scraper.session.get_calls == []
    assert len(scraper.session.post_calls) == 1
    _, data = scraper.session.post_calls[0]
    assert data == {"athlete": 48787, "type": "SB"}


def test_parses_season_bests_from_sb_page():
    scraper = MinfriidrettsScraper()
    athlete = scraper._parse_athlete_profile(
        (FIXTURES / "profile_sb.html").read_text(), 48787
    )

    # SB differs from the all-time PR: 14.03 this season vs 13.88 all-time.
    sb_100m = athlete.get_pb("100 meter")
    assert sb_100m is not None
    assert sb_100m.get_result_formatted() == "14.03"


# --- lookup_pb_sb -----------------------------------------------------------

class _FakeScraper:
    """Stand-in scraper: one search, per-view canned profiles, with counters."""

    def __init__(self):
        self.search_calls = 0
        self.profile_views = []

    def search_athletes_by_surname(self, surname):
        self.search_calls += 1
        return [
            SearchCandidate(id=1, name="Tangen, Aurora Molund",
                            club=None, birth_date="01.01.2009"),
        ]

    def fetch_athlete_profile(self, athlete_id, view="PR"):
        self.profile_views.append(view)
        value = "13,88" if view == "PR" else "14,03"
        athlete = Athlete(id=athlete_id, name="Aurora Molund Tangen")
        athlete.add_result(Result(
            athlete_name="Aurora Molund Tangen", club="", event="100 meter",
            result=value, indoor=False,
        ))
        return athlete


def test_lookup_pb_sb_matches_once_and_returns_both():
    service = PBLookupService()
    service.scraper = _FakeScraper()

    pb, sb = service.lookup_pb_sb(
        "Aurora Molund Tangen", club="IL i BUL Tromsø", birth_date="",
        event="100m", category="J17", competition_year=2026,
    )

    assert pb is not None and pb.get_result_formatted() == "13.88"
    assert sb is not None and sb.get_result_formatted() == "14.03"
    # The expensive search/match runs once; both views are then read.
    assert service.scraper.search_calls == 1
    assert service.scraper.profile_views == ["PR", "SB"]


def test_lookup_pb_sb_returns_none_pair_when_unmatched():
    class _NoCandidates(_FakeScraper):
        def search_athletes_by_surname(self, surname):
            self.search_calls += 1
            return []

    service = PBLookupService()
    service.scraper = _NoCandidates()

    pb, sb = service.lookup_pb_sb(
        "Nobody Here", club="", birth_date="", event="100m",
        category="J17", competition_year=2026,
    )

    assert pb is None and sb is None
    assert service.scraper.profile_views == []  # never fetched a profile


# --- best across indoor + outdoor ------------------------------------------

class _IndoorOutdoorScraper:
    """Profiles whose best high jump is indoor (1.25) above the outdoor (1.15)."""

    def search_athletes_by_surname(self, surname):
        return [SearchCandidate(id=1, name="Fosse, Sigurd",
                                club=None, birth_date="01.01.2012")]

    def fetch_athlete_profile(self, athlete_id, view="PR"):
        athlete = Athlete(id=athlete_id, name="Sigurd Fosse")
        athlete.add_result(Result(athlete_name="Sigurd Fosse", club="",
                                  event="Høyde", result="1,15", indoor=False))
        athlete.add_result(Result(athlete_name="Sigurd Fosse", club="",
                                  event="Høyde", result="1,25", indoor=True))
        return athlete


def test_lookup_takes_best_across_indoor_and_outdoor():
    service = PBLookupService()
    service.scraper = _IndoorOutdoorScraper()

    pb, sb = service.lookup_pb_sb(
        "Sigurd Fosse", club="", birth_date="", event="Høyde",
        category="G14", competition_year=2026,
    )

    # Field event: the indoor 1.25 beats the outdoor 1.15.
    assert pb is not None and pb.get_result_formatted() == "1.25"
    assert sb is not None and sb.get_result_formatted() == "1.25"

