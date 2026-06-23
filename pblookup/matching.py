"""Name matching and normalization utilities."""
import re
from datetime import date
from typing import List, Optional, Tuple
from rapidfuzz import fuzz

from .models import SearchCandidate


def normalize_norwegian_name(name: str) -> str:
    """Normalize Norwegian names for better matching."""
    if not name:
        return ""
        
    # Convert to lowercase and strip whitespace
    normalized = name.lower().strip()
    
    # Handle common Norwegian character variations
    char_mappings = {
        'æ': 'ae', 'ø': 'o', 'å': 'aa',
        'é': 'e', 'è': 'e', 'ê': 'e',
        'ü': 'u', 'ö': 'o', 'ä': 'a'
    }
    
    for norwegian_char, replacement in char_mappings.items():
        normalized = normalized.replace(norwegian_char, replacement)
    
    # Drop separators so "Surname, First" and "First Surname" compare equal once
    # token order is normalized (the search site lists "Surname, First").
    normalized = normalized.replace(',', ' ')

    # Remove extra whitespace and normalize
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


def extract_surname(full_name: str) -> str:
    """Extract surname (last name) from full name."""
    parts = full_name.strip().split()
    return parts[-1] if parts else ""


def calculate_name_similarity(candidate_name: str, target_name: str) -> float:
    """Calculate similarity score between two names."""
    if not candidate_name or not target_name:
        return 0.0
    
    # Normalize both names
    normalized_candidate = normalize_norwegian_name(candidate_name)
    normalized_target = normalize_norwegian_name(target_name)
    
    # Use multiple similarity metrics
    ratio = fuzz.ratio(normalized_candidate, normalized_target)
    token_ratio = fuzz.token_sort_ratio(normalized_candidate, normalized_target)
    partial_ratio = fuzz.partial_ratio(normalized_candidate, normalized_target)
    
    # Return the maximum score
    return max(ratio, token_ratio, partial_ratio) / 100.0


def calculate_club_similarity(candidate_club: str, target_club: str) -> float:
    """Calculate similarity score between club names."""
    if not candidate_club or not target_club:
        return 0.0 if candidate_club != target_club else 1.0
    
    # Normalize club names
    normalized_candidate = normalize_norwegian_name(candidate_club)
    normalized_target = normalize_norwegian_name(target_club)
    
    # Handle common abbreviations
    abbreviations = {
        'if': 'idrettforening',
        'il': 'idrettlag',
        'tif': 'turn og idrettforening',
        'sk': 'sportsklub',
        'bk': 'ballklubb',
        'fk': 'fotballklubb'
    }
    
    for abbr, full in abbreviations.items():
        normalized_candidate = normalized_candidate.replace(f' {abbr}', f' {full}')
        normalized_target = normalized_target.replace(f' {abbr}', f' {full}')
    
    return fuzz.ratio(normalized_candidate, normalized_target) / 100.0


def parse_birth_date(date_str: str) -> Tuple[int, int, int]:
    """Parse Norwegian date format (DD.MM.YYYY) into day, month, year."""
    if not date_str:
        return 0, 0, 0
    
    date_str = date_str.strip()
    
    # Handle year-only format (e.g., "2009")
    if re.match(r'^\d{4}$', date_str):
        return 0, 0, int(date_str)
    
    # Handle DD.MM.YYYY or DD.MM.YY format
    match = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', date_str)
    if not match:
        return 0, 0, 0
    
    day, month, year = map(int, match.groups())
    
    # Handle 2-digit years
    if year < 100:
        if year > 50:  # Assume 1950s+
            year += 1900
        else:  # Assume 2000s
            year += 2000
    
    return day, month, year


def calculate_birth_date_similarity(candidate_date: str, target_date: str) -> float:
    """Calculate similarity between birth dates."""
    if not candidate_date or not target_date:
        return 0.0 if candidate_date != target_date else 1.0
    
    candidate_day, candidate_month, candidate_year = parse_birth_date(candidate_date)
    target_day, target_month, target_year = parse_birth_date(target_date)
    
    if candidate_year == 0 or target_year == 0:
        return 0.0
    
    # Exact match
    if (candidate_day, candidate_month, candidate_year) == (target_day, target_month, target_year):
        return 1.0
    
    # Same year and month (day might be off)
    if candidate_year == target_year and candidate_month == target_month:
        return 0.8
    
    # Same year (different month)
    if candidate_year == target_year:
        return 0.6
    
    # Different years but close
    year_diff = abs(candidate_year - target_year)
    if year_diff <= 1:
        return 0.4
    elif year_diff <= 2:
        return 0.2
    
    return 0.0


def get_birth_year_from_date(date_str: str) -> Optional[int]:
    """Extract birth year from date string."""
    _, _, year = parse_birth_date(date_str)
    return year if year > 0 else None


def calculate_age_in_year(birth_year: int, competition_year: int) -> int:
    """Calculate athlete's age in a given competition year.
    
    In athletics, age category is determined by the year you turn that age,
    not your actual age on competition day.
    """
    return competition_year - birth_year


def parse_age_category(category: str) -> Optional[int]:
    """Parse the lower-bound age from a category string like 'J15', 'W50'.

    Returns the youngest age the category covers, or None if not parseable
    (e.g. 'Senior'). See parse_age_category_range for the full range.
    """
    rng = parse_age_category_range(category)
    return rng[0] if rng else None


# Masters (veteran) classes start at 35 and run in 5-year bands (W50 = 50-54).
_MASTERS_MIN_AGE = 35


def parse_age_category_range(category: str) -> Optional[Tuple[int, int]]:
    """Parse a category string into an inclusive (low, high) age range.

    Youth classes are a single year (the year you turn that age): 'J15' ->
    (15, 15). Masters classes are 5-year bands: 'W50' -> (50, 54), 'M35' ->
    (35, 39). Returns None for classes with no fixed age (Senior/Veteran) or
    when the string can't be parsed.

    Norwegian/international categories:
    - J = Jenter (girls), G = Gutter (boys) for youth
    - K = Kvinner (women), M = Menn (men), W = women masters
    - Numbers indicate age (youth 10-19) or the band floor (masters 35+)
    - G-rekrutt / J-rekrutt = age 10 (recruitment class)
    """
    if not category:
        return None

    category = category.upper().strip()

    # Recruitment (recruitment) categories - age 10
    if category in ('G-REKRUTT', 'J-REKRUTT', 'REKRUTT'):
        return (10, 10)

    # Under-X classes
    if category in ('U20', 'U-20'):
        return (19, 19)
    if category in ('U23', 'U-23'):
        return (22, 22)

    # Senior/Veteran have no fixed age band
    if category in ('SENIOR', 'SEN', 'VETERAN', 'VET'):
        return None

    # Letter prefix + age, e.g. J15, G12, M17, K15, W50, M35.
    match = re.match(r'^[A-ZÆØÅ]+[\s-]*(\d{1,2})$', category)
    if not match:
        match = re.match(r'^(\d{1,2})$', category)
    if match:
        age = int(match.group(1))
        if age >= _MASTERS_MIN_AGE:
            return (age, age + 4)  # 5-year masters band
        return (age, age)

    return None


def validate_age_category(
    candidate_birth_date: str,
    expected_category: str,
    competition_year: Optional[int] = None
) -> Tuple[bool, float]:
    """Validate if candidate's birth year matches expected age category.
    
    Args:
        candidate_birth_date: Candidate's birth date (DD.MM.YYYY)
        expected_category: Expected category like 'J15', 'G12', 'W50'
        competition_year: Year of competition (defaults to current year)
        
    Returns:
        Tuple of (is_valid, score) where:
        - is_valid: True if age matches category (inside band, or off by one)
        - score: 1.0 inside the band, 0.5 off-by-one at a band edge, else 0.0
    """
    if not candidate_birth_date or not expected_category:
        return False, 0.0  # Can't validate without both, reject match

    age_range = parse_age_category_range(expected_category)
    if age_range is None:
        return True, 0.5  # Can't pin an age (e.g. Senior), allow match

    birth_year = get_birth_year_from_date(candidate_birth_date)
    if birth_year is None:
        return False, 0.0  # Can't parse birth date, reject match

    if competition_year is None:
        competition_year = date.today().year

    actual_age = calculate_age_in_year(birth_year, competition_year)
    low, high = age_range

    # Inside the band (exact age for youth, 5-year span for masters)
    if low <= actual_age <= high:
        return True, 1.0

    # Off by one year at either edge (edge case or data issue)
    if actual_age == low - 1 or actual_age == high + 1:
        return True, 0.5

    # Clearly outside - wrong person
    return False, 0.0


def find_best_match(candidates: List[SearchCandidate], 
                   target_name: str,
                   target_club: str = "",
                   target_birth_date: str = "",
                   expected_category: str = "",
                   competition_year: Optional[int] = None,
                   min_score: float = 0.6) -> Optional[SearchCandidate]:
    """Find the best matching candidate athlete.
    
    Args:
        candidates: List of candidate athletes from search
        target_name: Full name to match
        target_club: Club affiliation (optional)
        target_birth_date: Birth date in DD.MM.YYYY format (optional)
        expected_category: Age category like 'J15', 'G12' for validation (optional)
        competition_year: Year of competition for age validation (defaults to current year)
        min_score: Minimum similarity score to accept a match
        
    Returns:
        Best matching candidate or None if no good match found
    """
    if not candidates:
        return None
    
    best_candidate = None
    best_score = 0.0
    
    for candidate in candidates:
        # Age category is a hard filter, but only when we can actually evaluate
        # it: the category must be parseable to an age band and the candidate
        # must have a birth date. Otherwise age is simply an absent signal.
        age_present = False
        age_score = 0.0
        if expected_category:
            age_range = parse_age_category_range(expected_category)
            candidate_year = get_birth_year_from_date(candidate.birth_date or "")
            if age_range is not None and candidate_year is not None:
                age_valid, age_score = validate_age_category(
                    candidate.birth_date or "",
                    expected_category,
                    competition_year,
                )
                if not age_valid:
                    candidate.similarity_score = 0.0
                    continue  # Hard reject: wrong age band
                age_present = True

        # Weight only the signals we actually have. Name is always present;
        # birth date, age and club count only when both sides supply them, so a
        # missing club or birth date neither helps nor penalizes (the score is
        # renormalized over the present signals).
        terms: List[Tuple[float, float]] = [
            (0.5, calculate_name_similarity(candidate.name, target_name))
        ]
        if target_birth_date and candidate.birth_date:
            terms.append(
                (0.2, calculate_birth_date_similarity(
                    candidate.birth_date, target_birth_date))
            )
        if age_present:
            terms.append((0.2, age_score))
        if target_club and candidate.club:
            terms.append(
                (0.1, calculate_club_similarity(candidate.club, target_club))
            )

        weight_sum = sum(weight for weight, _ in terms)
        overall_score = sum(weight * score for weight, score in terms) / weight_sum

        # Update candidate with calculated score
        candidate.similarity_score = overall_score
        
        if overall_score > best_score and overall_score >= min_score:
            best_score = overall_score
            best_candidate = candidate
    
    return best_candidate


def extract_name_variants(name: str) -> List[str]:
    """Generate common variants of a Norwegian name."""
    variants = [name]
    
    # Add normalized version
    normalized = normalize_norwegian_name(name)
    if normalized != name.lower():
        variants.append(normalized)
    
    # Add version with Norwegian characters
    norwegian_chars = {'ae': 'æ', 'aa': 'å', 'o': 'ø'}
    norwegian_version = normalized
    for eng, nor in norwegian_chars.items():
        norwegian_version = norwegian_version.replace(eng, nor)
    if norwegian_version != normalized:
        variants.append(norwegian_version)
    
    # Add parts of the name for partial matching
    parts = name.split()
    if len(parts) > 1:
        # Add first and last name separately
        variants.append(parts[0])  # First name
        variants.append(parts[-1])  # Last name
        
        # Add combinations
        if len(parts) > 2:
            variants.append(f"{parts[0]} {parts[-1]}")  # First + Last
    
    return list(set(variants))  # Remove duplicates
