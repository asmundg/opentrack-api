"""Which lanes a track race prefers, shared by the lane plan and the lane draw."""

import re

# Lane preference for staggered races, best-seeded first: the outer three, then
# the inner pair plus lane 8, and finally the two tightest bends.
STAGGERED_LANE_ORDER = [5, 6, 7, 3, 4, 8, 1, 2]


def is_staggered(discipline: str) -> bool:
    """Whether a race is run round a bend in lanes, so it starts staggered.

    Covers 200m-400m flat and hurdles, and all relays. Sprints down the
    straight (60m, 100m, 110H) are not staggered. Accepts OpenTrack codes
    ("200H", "4x100m") and scheduler names ("200m hekk", "4x60m stafett").
    """
    flat = re.match(r"^(\d+)(m|H|m hekk)$", discipline)
    if flat:
        return 200 <= int(flat.group(1)) <= 400
    return bool(re.match(r"^\d+x\d+m( stafett)?$", discipline))


def lane_preference(lanes: int, staggered: bool = False) -> list[int]:
    """Lane numbers in seeding preference order, fastest athlete first.

    Straight races draw the middle lanes first, working outwards and preferring
    the inner lane of each pair: 8 lanes give 4, 5, 3, 6, 2, 7, 1, 8.

    Staggered races draw 5, 6, 7 first, then 3, 4, 8, then 1, 2, keeping the
    fastest off the tightest bends.
    """
    if staggered:
        return [lane for lane in STAGGERED_LANE_ORDER if lane <= lanes]
    return sorted(range(1, lanes + 1), key=lambda lane: (abs(2 * lane - lanes - 1), lane))
