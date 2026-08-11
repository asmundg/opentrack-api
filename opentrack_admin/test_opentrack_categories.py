"""Implement weights for the category codes OpenTrack itself emits.

OpenTrack derives a competitor's category from birth year, so its pool data
carries codes the Isonen import never produces: raw ages below 10 ("G9"),
gender-suffixed U-codes ("U23K") and masters codes ("M75").
"""

import pytest

from .events import get_implement_weight


@pytest.mark.parametrize(
    "category,expected",
    [("G9", "2"), ("J7", "2"), ("G10", "2"), ("J10", "2")],
)
def test_under_10s_throw_the_rekrutt_shot(category, expected):
    assert get_implement_weight("SP", category) == expected


@pytest.mark.parametrize("event", ["DT", "JT", "HT"])
def test_under_10s_are_not_offered_the_other_throws(event):
    assert get_implement_weight(event, "G9") is None


def test_u_codes_take_gender_from_their_suffix():
    assert get_implement_weight("SP", "U23K") == "4"
    assert get_implement_weight("SP", "U23M") == "7,26"
    # Javelin is where U20 and U23 women differ.
    assert get_implement_weight("JT", "U20K") == "0,5"
    assert get_implement_weight("JT", "U23K") == "0,6"
    # The bare form stays men's, as before.
    assert get_implement_weight("SP", "U23") == "7,26"


def test_opentrack_masters_codes_use_the_masters_schedule():
    assert get_implement_weight("SP", "M75") == "4"
    assert get_implement_weight("DT", "M75") == "1"
    assert get_implement_weight("HT", "M75") == "4"
    assert get_implement_weight("SP", "K75") == "2"
    # Same answer as the canonical short form.
    assert get_implement_weight("SP", "M75") == get_implement_weight("SP", "MV75-79")


def test_unknown_categories_still_fail_loudly():
    with pytest.raises(ValueError):
        get_implement_weight("SP", "X42")
