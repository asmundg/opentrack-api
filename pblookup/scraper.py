"""Web scraper for minfriidrettsstatistikk.info"""
import re
import sys
import time
from datetime import datetime
from functools import wraps
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .models import Athlete, Result, SearchCandidate
from .events import standardize_event_name, is_indoor_event


def rate_limit(calls_per_second: float = 1.0):
    """Decorator to rate limit function calls."""
    min_interval = 1.0 / calls_per_second
    last_called = [0.0]
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator


class MinfriidrettsScraper:
    """Scraper for minfriidrettsstatistikk.info website."""
    
    BASE_URL = "https://www.minfriidrettsstatistikk.info"
    SEARCH_URL = f"{BASE_URL}/php/UtoverSok.php"
    PROFILE_URL = f"{BASE_URL}/php/UtoverStatistikk.php"
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        })
        
    @rate_limit(0.5)  # 1 request every 2 seconds
    def search_athletes_by_surname(self, surname: str) -> List[SearchCandidate]:
        """Search for athletes by surname."""
        try:
            payload = {"showathlete": surname, "cmd": "SearchAthlete"}
            if self.debug:
                print(f"DEBUG: Searching URL: {self.SEARCH_URL}", file=sys.stderr)
                print(f"DEBUG: Search payload: {payload}", file=sys.stderr)
                
            response = self.session.post(self.SEARCH_URL, data=payload, timeout=10)
            response.raise_for_status()
            
            if self.debug:
                print(f"DEBUG: Response status: {response.status_code}", file=sys.stderr)
                print(f"DEBUG: Response length: {len(response.text)} characters", file=sys.stderr)
            
            return self._extract_athlete_candidates(response.text)
            
        except requests.RequestException as e:
            print(f"Error searching for surname '{surname}': {e}", file=sys.stderr)
            return []
    
    def _extract_athlete_candidates(self, html: str) -> List[SearchCandidate]:
        """Extract athlete candidates from search results HTML."""
        candidates = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find the results table
        results_div = soup.find('div', id='resultat')
        if not results_div:
            return candidates
            
        # Find the table with athlete results
        table = results_div.find('table')
        if not table:
            return candidates
            
        # Skip the header row and process data rows
        rows = table.find_all('tr')[1:]  # Skip header row
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 2:
                continue
                
            # First cell contains the link and name
            link_cell = cells[0]
            birth_cell = cells[1]
            
            # Extract link
            link = link_cell.find('a')
            if not link:
                continue
                
            # Extract athlete ID from URL - using correct parameter name
            href = link.get('href', '')
            match = re.search(r'showathl=(\d+)', href)
            if not match:
                continue
                
            athlete_id = int(match.group(1))
            athlete_name = link.text.strip()
            
            if not athlete_name:
                continue
                
            # Extract birth date from second cell
            birth_date = birth_cell.text.strip()
            
            # Validate birth date format
            if not re.match(r'\d{2}\.\d{2}\.\d{4}', birth_date) and not re.match(r'^\d{4}$', birth_date):
                birth_date = None
            
            # For now, we don't have club info in the search results
            # This would need to be fetched from the individual profile
            
            candidate = SearchCandidate(
                id=athlete_id,
                name=athlete_name,
                club=None,  # Not available in search results
                birth_date=birth_date,
                url=f"{self.PROFILE_URL}?showathlete={athlete_id}"
            )
            candidates.append(candidate)
            
        return candidates
    
    @rate_limit(0.5)  # 1 request every 2 seconds
    def fetch_athlete_profile(self, athlete_id: int) -> Optional[Athlete]:
        """Fetch complete athlete profile by ID."""
        try:
            url = f"{self.PROFILE_URL}?showathlete={athlete_id}"
            if self.debug:
                print(f"DEBUG: Fetching profile URL: {url}", file=sys.stderr)
                
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            if self.debug:
                print(f"DEBUG: Profile response status: {response.status_code}", file=sys.stderr)
                print(f"DEBUG: Profile response length: {len(response.text)} characters", file=sys.stderr)
            
            return self._parse_athlete_profile(response.text, athlete_id)
            
        except requests.RequestException as e:
            print(f"Error fetching profile for athlete {athlete_id}: {e}", file=sys.stderr)
            return None
    
    def _parse_athlete_profile(self, html: str, athlete_id: int) -> Optional[Athlete]:
        """Parse athlete profile HTML to extract personal bests."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract athlete name (usually in a header or title)
        athlete_name = self._extract_athlete_name(soup)
        if not athlete_name:
            return None
            
        # Extract birth date
        birth_date = self._extract_birth_date(soup)
        
        # Extract clubs
        clubs = self._extract_clubs(soup)
        
        # Create athlete object
        athlete = Athlete(
            id=athlete_id,
            name=athlete_name,
            birth_date=birth_date,
            clubs=clubs,
            last_updated=datetime.now()
        )
        
        # Extract outdoor and indoor records
        outdoor_results = self._extract_results(soup, indoor=False)
        indoor_results = self._extract_results(soup, indoor=True)
        
        for result in outdoor_results + indoor_results:
            athlete.add_result(result)
            
        return athlete
    
    def _extract_athlete_name(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract athlete name from profile page."""
        # Look for name in common header tags
        for tag in ['h1', 'h2', 'h3']:
            header = soup.find(tag)
            if header and header.text.strip():
                # Clean up the name (remove extra whitespace, etc.)
                name = re.sub(r'\s+', ' ', header.text.strip())
                if name and not name.isdigit():
                    return name
        
        # Fallback: look for name pattern in page text
        text = soup.get_text()
        name_match = re.search(r'^([A-ZÆØÅ][a-zæøå]+ [A-ZÆØÅ][a-zæøå]+)', text, re.MULTILINE)
        if name_match:
            return name_match.group(1)
            
        return None
    
    def _extract_birth_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract birth date from profile page."""
        text = soup.get_text()
        birth_match = re.search(r'\b(\d{2}\.\d{2}\.\d{4})\b', text)
        return birth_match.group(1) if birth_match else None
    
    def _extract_clubs(self, soup: BeautifulSoup) -> List[str]:
        """Extract club affiliations from profile page."""
        clubs = []
        text = soup.get_text()
        
        # Look for Norwegian club patterns (often end with IF, IL, TIF, etc.)
        club_matches = re.findall(r'\b([A-ZÆØÅ][a-zæøå\s]+ (?:IF|IL|TIF|SK|BK|FK))\b', text)
        for club in club_matches:
            club = club.strip()
            if club and club not in clubs:
                clubs.append(club)
                
        return clubs
    
    def _extract_results(self, soup: BeautifulSoup, indoor: bool = False) -> List[Result]:
        """Extract results from profile page."""
        results = []
        
        # This is a simplified version - the actual implementation would need
        # to parse the specific table structure of minfriidrettsstatistikk.info
        
        # Look for tables containing results
        tables = soup.find_all('table')
        
        for table in tables:
            # Determine if this is indoor or outdoor based on context
            table_text = table.get_text().lower()
            is_indoor_table = 'innendørs' in table_text or 'indoor' in table_text
            
            if is_indoor_table != indoor:
                continue
                
            # Extract rows from table
            rows = table.find_all('tr')
            
            for row in rows[1:]:  # Skip header row
                cells = row.find_all(['td', 'th'])
                if len(cells) < 3:  # Need at least event, result, and some context
                    continue
                    
                result = self._parse_result_row(cells, indoor)
                if result:
                    results.append(result)
                    
        return results
    
    def _parse_result_row(self, cells, indoor: bool) -> Optional[Result]:
        """Parse a single result row from a table."""
        try:
            # This is a simplified parser - would need adjustment based on actual site structure
            if len(cells) < 4:
                return None
                
            event_cell = cells[0].get_text().strip()
            result_cell = cells[1].get_text().strip()
            
            if not event_cell or not result_cell:
                return None
                
            # Extract additional fields if available
            wind = None
            position = None
            club = None
            date = None
            venue = None
            
            # Parse additional cells for context
            for i, cell in enumerate(cells[2:], 2):
                cell_text = cell.get_text().strip()
                
                # Try to identify what this cell contains
                if re.match(r'[+\-]?\d+[,.]?\d*', cell_text) and i == 2:
                    wind = cell_text
                elif re.match(r'\d+(-h\d+)?', cell_text):
                    position = cell_text
                elif re.search(r'\d{2}\.\d{2}\.\d{2,4}', cell_text):
                    date_match = re.search(r'(\d{2}\.\d{2}\.\d{2,4})', cell_text)
                    if date_match:
                        date_str = date_match.group(1)
                        # Handle 2-digit years
                        if len(date_str.split('.')[-1]) == 2:
                            year = int(date_str.split('.')[-1])
                            if year > 50:  # Assume 1950s+
                                date_str = date_str[:-2] + '19' + date_str[-2:]
                            else:  # Assume 2000s
                                date_str = date_str[:-2] + '20' + date_str[-2:]
                        try:
                            date = datetime.strptime(date_str, '%d.%m.%Y')
                        except ValueError:
                            pass
                elif 'IF' in cell_text or 'IL' in cell_text or 'TIF' in cell_text:
                    club = cell_text
                else:
                    if not venue and len(cell_text) > 3:
                        venue = cell_text
            
            # Create result object
            result = Result(
                athlete_name="",  # Will be set by caller
                club=club or "",
                event=event_cell,  # Keep original event name, don't standardize here
                result=result_cell,
                date=date,
                venue=venue,
                wind=wind,
                indoor=indoor or is_indoor_event(event_cell),
                position=position
            )
            
            return result
            
        except Exception as e:
            print(f"Error parsing result row: {e}", file=sys.stderr)
            return None
