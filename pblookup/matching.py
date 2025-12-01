"""Name matching and normalization utilities."""
import re
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
    
    # Remove extra whitespace and normalize
    normalized = re.sub(r'\s+', ' ', normalized)
    
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
    
    # Handle DD.MM.YYYY or DD.MM.YY format
    match = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', date_str.strip())
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


def find_best_match(candidates: List[SearchCandidate], 
                   target_name: str,
                   target_club: str = "",
                   target_birth_date: str = "",
                   min_score: float = 0.6) -> Optional[SearchCandidate]:
    """Find the best matching candidate athlete."""
    if not candidates:
        return None
    
    best_candidate = None
    best_score = 0.0
    
    for candidate in candidates:
        # Calculate component scores
        name_score = calculate_name_similarity(candidate.name, target_name)
        club_score = calculate_club_similarity(candidate.club or "", target_club)
        birth_date_score = calculate_birth_date_similarity(candidate.birth_date or "", target_birth_date)
        
        # Weighted overall score
        # Name is most important, followed by birth date, then club
        overall_score = (
            name_score * 0.6 +
            birth_date_score * 0.3 +
            club_score * 0.1
        )
        
        # Bonus for exact birth date match
        if birth_date_score == 1.0:
            overall_score += 0.1
            
        # Bonus for exact club match
        if club_score == 1.0:
            overall_score += 0.05
        
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
