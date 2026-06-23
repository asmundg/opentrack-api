"""Tests for athlete name/club/age matching.

These exercise the three signals the matcher uses to disambiguate same-surname
candidates: name (order-invariant), age category (incl. masters 5-year bands),
and club. The driving case is "Berit Evensen-Amundsen" (W50), where the search
results list the name as "Evensen-Amundsen, Berit" with no club, and the
schedule provides no birth date.
"""

from pblookup.matching import (
    calculate_name_similarity,
    parse_age_category_range,
    validate_age_category,
    find_best_match,
)
from pblookup.models import SearchCandidate


# --- name sorting: "Surname, First" must match "First Surname" exactly ---

def test_name_match_is_order_and_comma_invariant():
    score = calculate_name_similarity(
        "Evensen-Amundsen, Berit", "Berit Evensen-Amundsen"
    )
    assert score >= 0.99


def test_name_match_distinguishes_first_names():
    berit = calculate_name_similarity(
        "Evensen-Amundsen, Berit", "Berit Evensen-Amundsen"
    )
    torgeir = calculate_name_similarity(
        "Evensen-Amundsen, Torgeir", "Berit Evensen-Amundsen"
    )
    assert berit > torgeir


# --- category parsing: masters W/M/K are 5-year bands ---

def test_masters_category_parses_to_band():
    assert parse_age_category_range("W50") == (50, 54)
    assert parse_age_category_range("M35") == (35, 39)
    assert parse_age_category_range("K55") == (55, 59)


def test_youth_category_parses_to_exact_age():
    assert parse_age_category_range("G15") == (15, 15)
    assert parse_age_category_range("J12") == (12, 12)


def test_rekrutt_and_senior_categories():
    assert parse_age_category_range("G-Rekrutt") == (10, 10)
    assert parse_age_category_range("Senior") is None
    assert parse_age_category_range("Kvinner Senior") is None


def test_masters_age_validation_uses_band():
    # Born 1974 -> 52 in 2026, inside W50 (50-54).
    assert validate_age_category("18.04.1974", "W50", 2026) == (True, 1.0)
    # Born 1976 -> 50 in 2026, lower edge of band.
    assert validate_age_category("12.01.1976", "W50", 2026) == (True, 1.0)
    # Born 1971 -> 55, one past the band -> tolerated as off-by-one.
    assert validate_age_category("01.01.1971", "W50", 2026) == (True, 0.5)
    # Born 1969 -> 57, clearly outside.
    assert validate_age_category("01.01.1969", "W50", 2026) == (False, 0.0)


def test_youth_age_validation_unchanged():
    assert validate_age_category("01.01.2011", "G15", 2026) == (True, 1.0)
    assert validate_age_category("01.01.2012", "G15", 2026) == (True, 0.5)
    assert validate_age_category("01.01.2014", "G15", 2026) == (False, 0.0)


# --- club: an absent candidate club must not penalize the match ---

def _evensen_amundsen_candidates():
    return [
        SearchCandidate(id=31078, name="Evensen-Amundsen, Berit",
                        club=None, birth_date="18.04.1974"),
        SearchCandidate(id=10032114, name="Evensen-Amundsen, Jonette Celia",
                        club=None, birth_date="17.04.2007"),
        SearchCandidate(id=10030183, name="Evensen-Amundsen, Julius",
                        club=None, birth_date="31.03.2009"),
        SearchCandidate(id=10023622, name="Evensen-Amundsen, Torgeir",
                        club=None, birth_date="12.01.1976"),
    ]


def test_berit_matches_despite_missing_club_and_birth():
    match = find_best_match(
        _evensen_amundsen_candidates(),
        target_name="Berit Evensen-Amundsen",
        target_club="Bardu Idrettslag",
        target_birth_date="",
        expected_category="W50",
        competition_year=2026,
    )
    assert match is not None
    assert match.id == 31078


def test_present_matching_club_still_helps():
    cands = [
        SearchCandidate(id=1, name="Hansen, Per", club="Bardu IL",
                        birth_date="01.01.1990"),
        SearchCandidate(id=2, name="Hansen, Per", club="Tromsø IL",
                        birth_date="01.01.1990"),
    ]
    match = find_best_match(
        cands,
        target_name="Per Hansen",
        target_club="Bardu Idrettslag",
        target_birth_date="01.01.1990",
        competition_year=2026,
    )
    assert match is not None
    assert match.id == 1
