"""Tests for result ranking (field vs time direction, indoor/outdoor merge).

Regression guard: field events whose names contain no 'm' (Høyde, Lengde, Kule,
Diskos, Spyd, Slegge) must still rank higher-is-better. The previous heuristic
keyed on the letter 'm' and ranked these backwards, hiding an athlete's true PB.
"""

from pblookup.events import better_result, is_better_result
from pblookup.models import Athlete, Result


def _r(event, value, indoor=False):
    return Result(athlete_name="x", club="", event=event, result=value, indoor=indoor)


def test_field_event_higher_is_better():
    assert is_better_result("Høyde", _r("Høyde", "1,25"), _r("Høyde", "1,15"))
    assert not is_better_result("Høyde", _r("Høyde", "1,15"), _r("Høyde", "1,25"))


def test_throw_with_weight_in_name_ranks_higher_is_better():
    assert is_better_result(
        "Kule 4,0kg", _r("Kule 4,0kg", "9,08"), _r("Kule 4,0kg", "7,91")
    )


def test_time_event_lower_is_better():
    assert is_better_result("600 meter", _r("600 meter", "1,46,98"),
                            _r("600 meter", "1,58,95"))
    assert not is_better_result("600 meter", _r("600 meter", "1,58,95"),
                                _r("600 meter", "1,46,98"))


def test_better_result_handles_missing_sides():
    a = _r("Høyde", "1,25")
    assert better_result("Høyde", a, None) is a
    assert better_result("Høyde", None, a) is a
    assert better_result("Høyde", None, None) is None


def test_athlete_add_result_keeps_better_field_mark_regardless_of_order():
    # Adding the weaker mark first must not stick: 1.25 should win for high jump.
    for first, second in (("1,15", "1,25"), ("1,25", "1,15")):
        athlete = Athlete(id=1, name="x")
        athlete.add_result(_r("Høyde", first))
        athlete.add_result(_r("Høyde", second))
        assert athlete.outdoor_pbs["Høyde"].result == "1,25"
