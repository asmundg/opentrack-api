"""Calculate Tyrving points using coefficient tables from rjukanfriidrett.no.

OpenTrack doesn't compute Tyrving points for 18/19 age groups.
This module fetches the official coefficient table and computes points locally.
"""

import json
import math
import urllib.request
from pathlib import Path

# Cache the coefficient table on disk to avoid re-fetching
_CACHE_PATH = Path(__file__).parent / ".tyrving_coefficients.json"
_BACKEND_URL = "https://rjukanfriidrett.no/rilfrioks/backendGetFrioksDatatables.php"
_CLUB_GUID = "897DB56B-3C18-4253-A1E5-DF31F2004B57"

# Map OpenTrack event names to calculator event names
_EVENT_NAME_MAP: dict[str, str] = {
    "60 meter": "60 m",
    "60 meter hekk": "60 m hekk",
    "80 meter": "80 m",
    "80 meter hekk": "80 m hekk",
    "100 meter": "100 m",
    "100 meter hekk": "100 m hekk",
    "110 meter hekk": "110 m hekk",
    "200 meter": "200 m",
    "200 meter hekk": "200 m hekk",
    "300 meter": "300 m",
    "300 meter hekk": "300 m hekk",
    "400 meter": "400 m",
    "400 meter hekk": "400 m hekk",
    "600 meter": "600 m",
    "800 meter": "800 m",
    "1000 meter": "1000 m",
    "1500 meter": "1500 m",
    "2000 meter": "2000 m",
    "3000 meter": "3000 m",
    "5000 meter": "5000 m",
    "10000 meter": "10000 m",
    "Høyde uten tilløp": "Høyde u.t.",
    "Lengde uten tilløp": "Lengde u.t.",
    # These are already matching:
    "Høyde": "Høyde",
    "Lengde": "Lengde",
    "Kule": "Kule",
    "Tresteg": "Tresteg",
    "Diskos": "Diskos",
    "Spyd": "Spyd",
    "Stav": "Stav",
    "Slegge": "Slegge",
}

# Map OpenTrack category names to calculator class names
# OpenTrack uses "G18/19", calculator uses "G-18/19"
_CATEGORY_MAP: dict[str, str] = {}


def _map_category(opentrack_category: str) -> str:
    """Convert OpenTrack category (e.g. 'G18/19') to calculator class (e.g. 'G-18/19')."""
    if opentrack_category in _CATEGORY_MAP:
        return _CATEGORY_MAP[opentrack_category]

    # OpenTrack: "G17", "J18/19" → Calculator: "G-17", "J-18/19"
    cat = opentrack_category
    if len(cat) >= 2 and cat[0] in ("G", "J", "K", "M") and cat[1].isdigit():
        cat = cat[0] + "-" + cat[1:]
    return cat


def _map_event_name(opentrack_event: str) -> str:
    """Convert OpenTrack event name to calculator event name."""
    return _EVENT_NAME_MAP.get(opentrack_event, opentrack_event)


def _fetch_coefficients() -> list[dict[str, str]]:
    """Fetch Tyrving coefficient table from the calculator backend."""
    url = f"{_BACKEND_URL}?DataType=application/json&ClubGUID={_CLUB_GUID}&tableName=Tyrving"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        },
    )
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["Tyrving"]


def _load_coefficients() -> list[dict[str, str]]:
    """Load coefficients from cache, fetching if needed."""
    if _CACHE_PATH.exists():
        with open(_CACHE_PATH) as f:
            return json.load(f)

    print("Fetching Tyrving coefficient table...")
    coefficients = _fetch_coefficients()
    with open(_CACHE_PATH, "w") as f:
        json.dump(coefficients, f)
    print(f"Cached {len(coefficients)} coefficient records.")
    return coefficients


def _get_record(
    coefficients: list[dict[str, str]], klasse: str, ovelse: str, eventinfo: str
) -> dict[str, str] | None:
    """Find the matching coefficient record."""
    ovelse = ovelse.replace(", finale", "")
    for rec in coefficients:
        if (
            rec["Klasse"] == klasse
            and rec["Øvelse"] == ovelse
            and rec["EventInfo"] == eventinfo
        ):
            return rec
    return None


def _get_default_record(
    coefficients: list[dict[str, str]], klasse: str, ovelse: str
) -> dict[str, str] | None:
    """Find the default coefficient record for a class/event."""
    ovelse = ovelse.replace(", finale", "")
    for rec in coefficients:
        if (
            rec["Klasse"] == klasse
            and rec["Øvelse"] == ovelse
            and rec["Def"] == "Sann"
        ):
            return rec
    return None


def _time_string_to_ms(time_str: str) -> int:
    """Convert a time string to milliseconds. Port of JsTidIStringToMs."""
    s = str(time_str)
    s = s.replace(",", ".").replace(":", ".")

    parts = s.split(".")
    n = len(parts)

    hh = mm = ss = ms_str = "0"
    if n == 4:
        hh, mm, ss, ms_str = parts
    elif n == 3:
        mm, ss, ms_str = parts
    elif n == 2:
        ss, ms_str = parts
    elif n == 1:
        ss = parts[0]
    else:
        return 0

    hh = hh.strip()
    mm = mm.strip()
    ss = ss.strip()
    ms_str = ms_str.strip() or "0"

    try:
        ms_val = int(ms_str)
        ms_len = len(ms_str)
        if ms_len == 2:
            ms_val *= 10
        elif ms_len == 1:
            ms_val *= 100

        return ms_val + int(ss) * 1000 + int(mm) * 60 * 1000 + int(hh) * 3600 * 1000
    except ValueError:
        return -1


def _calc_tyrving_points(rec: dict[str, str], result_str: str) -> int:
    """Calculate Tyrving points from a coefficient record and result string.

    Port of jsCalcTyrvingPoeng from TyrvingKalk.js.
    """
    if not result_str or result_str == "NM":
        return 0

    m1 = float(rec["M1"].replace(",", "."))
    m2 = float(rec["M2"].replace(",", "."))
    m3 = float(rec["M3"].replace(",", "."))
    tilleggsfaktor = int(rec["TillegsFaktor"])
    teknisk = rec["Tekknisk"] == "Sann"

    if teknisk:
        # Field event
        utgangspunkt = float(rec["Uttgangspunkt"].replace(",", "."))
        if utgangspunkt == 0:
            return 0

        try:
            resultat = float(result_str)
        except ValueError:
            return 0
        if resultat == 0:
            return 0

        ekstra = round((resultat - utgangspunkt) * 100) / 100
        ekstrapoeng = round(ekstra * m1 * tilleggsfaktor * 100) / 100
        tyrving_poeng = 1000 + ekstrapoeng

        if m2 != 0 and resultat < utgangspunkt:
            threshold = round(utgangspunkt * 0.8 * 100) / 100
            if round(resultat * 100) / 100 < threshold:
                trekk80 = (utgangspunkt - utgangspunkt * 0.8) * m2 * tilleggsfaktor
                trekk_rest = (utgangspunkt * 0.8 - resultat) * m3
                trekk_rest = round(trekk_rest * tilleggsfaktor * 100) / 100
                tyrving_poeng = 1000 - trekk80 - trekk_rest
            else:
                trekk80 = (
                    (utgangspunkt - max(resultat, utgangspunkt * 0.8))
                    * m2
                    * tilleggsfaktor
                )
                tyrving_poeng = 1000 - trekk80

        if resultat < 0:
            tyrving_poeng = 0
    else:
        # Running event
        resultat_ms = _time_string_to_ms(result_str)
        if resultat_ms <= 0 or math.isnan(resultat_ms):
            return 0

        # Round based on tilleggsfaktor
        if tilleggsfaktor == 100:
            resultat_ms = float(round(resultat_ms / 10 - 0.49999)) * 10
        elif tilleggsfaktor == 10:
            resultat_ms = float(round(resultat_ms / 10 - 0.49999)) * 10
        elif tilleggsfaktor == 0:
            resultat_ms = float(round(resultat_ms / 1000 - 0.49999)) * 1000

        utgangspunkt_str = rec["Uttgangspunkt"].replace(",", ".")
        utgangspunkt_ms = _time_string_to_ms(utgangspunkt_str)

        extra = float(utgangspunkt_ms - resultat_ms)
        tyrving_poeng = 1000 + (extra * m1 * tilleggsfaktor / 1000)

    rounded = round(tyrving_poeng - 0.49999)
    return max(rounded, 0)


def calc_points(
    category: str, event_name: str, performance: str
) -> int | None:
    """Calculate Tyrving points for a given category, event and performance.

    Args:
        category: OpenTrack category (e.g. "G18/19", "J17")
        event_name: OpenTrack event name (e.g. "60 meter", "Høyde uten tilløp")
        performance: Result string (e.g. "7.63", "2.56", "2:52.13")

    Returns:
        Computed Tyrving points, or None if no matching coefficient found.
    """
    if not performance or performance == "NM":
        return None

    coefficients = _load_coefficients()
    klasse = _map_category(category)
    ovelse = _map_event_name(event_name)

    # Try default record first, then eventinfo="0"
    rec = _get_default_record(coefficients, klasse, ovelse)
    if rec is None:
        rec = _get_record(coefficients, klasse, ovelse, "0")
    if rec is None:
        return None

    return _calc_tyrving_points(rec, performance)


def refresh_coefficients() -> None:
    """Force re-fetch of the coefficient table."""
    if _CACHE_PATH.exists():
        _CACHE_PATH.unlink()
    _load_coefficients()
