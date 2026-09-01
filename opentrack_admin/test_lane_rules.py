"""Lane draw rules per race type: straight, staggered, and group starts."""

from .sync import is_group_start, is_staggered, lane_preference


def test_sprints_down_the_straight_are_not_staggered():
    for code in ("60m", "100m", "60H", "100H"):
        assert not is_staggered(code)


def test_bend_races_and_relays_are_staggered():
    for code in ("200m", "400m", "200H", "400H", "4x60m", "4x100m"):
        assert is_staggered(code)


def test_distance_races_start_as_a_group():
    """600m and 1500m up are run off the waterfall, not in lanes."""
    for code in ("600m", "1500m", "3000m", "5000m"):
        assert is_group_start(code)


def test_lane_races_are_not_group_starts():
    for code in ("60m", "100m", "200m", "400m", "800m", "60H", "4x60m", "LJ"):
        assert not is_group_start(code)


def test_a_group_start_is_never_also_staggered():
    """The two rules must not both claim a race, or the draw is ambiguous."""
    for code in ("600m", "1500m", "3000m", "5000m"):
        assert not (is_group_start(code) and is_staggered(code))


def test_straight_draw_prefers_the_middle_lanes():
    assert lane_preference(8) == [4, 5, 3, 6, 2, 7, 1, 8]


def test_staggered_draw_keeps_the_fastest_off_the_tightest_bends():
    assert lane_preference(8, staggered=True)[:3] == [5, 6, 7]
