import json
import urllib.request
import urllib.error
import re

def fetch_json_data(url):
    """Fetch JSON data from a given URL using only standard library."""
    if not url.endswith('/json/'):
        if url.endswith('/'):
            url += 'json/'
        else:
            url += '/json/'
            
    print(f"Fetching data from {url}")
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data
    except urllib.error.HTTPError as e:
        raise urllib.error.HTTPError(url, e.code, f"HTTP Error: {e.code} - {e.reason}", e.hdrs, e.fp)
    except urllib.error.URLError as e:
        raise urllib.error.URLError(f"URL Error: {e.reason}")
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"JSON Decode Error from {url}: {e.msg}", e.doc, e.pos)

def process_local_json(filepath):
    """Process a local JSON file instead of fetching from URL."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {filepath}")
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"JSON Decode Error in {filepath}: {e.msg}", e.doc, e.pos)

def get_meeting_name(json_data):
    """Extract meeting name from OpenTrack JSON data."""
    return json_data['fullName']

def create_safe_filename(meeting_name):
    """Create a safe filename from the meeting name."""
    safe_name = re.sub(r'[^\w\s-]', '', meeting_name)
    safe_name = re.sub(r'[\s-]+', '_', safe_name)
    return safe_name

def clean_event_name(event_name):
    """Clean event name by removing category prefix if present."""
    # Strip category prefix from event name if present
    # For example, convert "G16 200 meter" to just "200 meter"
    event_name_parts = event_name.split(' ', 1)
    clean_name = event_name
    
    # Common Norwegian category prefixes: G (Gutter/Boys), J (Jenter/Girls), 
    # K (Kvinner/Women), M (Menn/Men), followed by age group
    if len(event_name_parts) > 1:
        first_part = event_name_parts[0]
        # Check if first part starts with a category letter and contains numbers (age)
        if (first_part.startswith(('G', 'J', 'K', 'M')) and 
            any(char.isdigit() for char in first_part)):
            clean_name = event_name_parts[1]
    
    return clean_name

def load_opentrack_data(input_source):
    """Load OpenTrack data from URL or local file."""
    if input_source.startswith('http://') or input_source.startswith('https://'):
        return fetch_json_data(input_source)
    else:
        return process_local_json(input_source)
