import json
import csv
import sys
import urllib.request
import urllib.error

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

def parse_opentrack_json(data):
    """Parse OpenTrack JSON and extract required fields."""
    results = []
    
    # Build a dictionary of competitors by bib number
    bib_dict = {}
    
    for competitor in data['competitors']:
        # Require fields instead of using .get() with fallbacks
        first_name = competitor['firstName']
        last_name = competitor['lastName']
        name = f"{first_name} {last_name}".strip()
        
        # Get club information from teamName field
        club = competitor['teamName']
        category = competitor['category']
        
        # Use sortBib as the key for the bib dictionary if available
        if 'sortBib' in competitor:
            bib = competitor['sortBib'].lstrip('0')  # Remove leading zeros
            bib_dict[bib] = {
                'name': name, 
                'club': club,
                'category': category
            }
    
    # Process events
    events = data['events']
    
    meeting_name = data['fullName']
    
    for event in events:
        # Require fields
        event_name = event['name']
        
        # Strip category prefix from event name if present
        # For example, convert "G16 200 meter" to just "200 meter"
        # First check if the event name starts with a category code
        event_name_parts = event_name.split(' ', 1)
        clean_event_name = event_name
        
        # Common Norwegian category prefixes: G (Gutter/Boys), J (Jenter/Girls), 
        # K (Kvinner/Women), M (Menn/Men), followed by age group
        if len(event_name_parts) > 1:
            first_part = event_name_parts[0]
            # Check if first part starts with a category letter and contains numbers (age)
            if (first_part.startswith(('G', 'J', 'K', 'M')) and 
                any(char.isdigit() for char in first_part)):
                clean_event_name = event_name_parts[1]
                
        # Process units within events
        for unit in event['units']:
            # Process results within units
            for result in unit['results']:
                # Skip results without athlon points or catpos
                if 'athlonPoints' not in result or not result.get('athlonPoints') or 'catpos' not in result:
                    continue
                
                bib = result['bib']
                athlon_points = result['athlonPoints']
                
                competitor_info = bib_dict[bib]
                competitor_name = competitor_info['name']
                club_name = competitor_info['club']
                category = competitor_info['category']
                
                # Add to results list
                results.append({
                    'Startnummer': bib,
                    'Navn': competitor_name,
                    'Klubb': club_name,
                    'Klasse': category,
                    'Øvelse': clean_event_name,
                    'Stevne': meeting_name,
                    'Tyrvingpoeng': athlon_points
                })
    
    return results

def save_to_csv(data, filename='opentrack_results.csv'):
    """Save parsed data to CSV."""
    fieldnames = ['Startnummer', 'Navn', 'Klubb', 'Klasse', 'Øvelse', 'Stevne', 'Tyrvingpoeng']
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    
    print(f"Data saved to {filename}")

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

def main():
    # Check if argument is provided
    if len(sys.argv) <= 1:
        sys.exit("Please provide either a URL or a local JSON file path.")
    
    input_source = sys.argv[1]
    
    # Determine if input is a local file or URL
    try:
        if input_source.startswith('http://') or input_source.startswith('https://'):
            json_data = fetch_json_data(input_source)
        else:
            json_data = process_local_json(input_source)
        
        # Generate a filename based on the meeting name
        meeting_name = ""
        if 'fullName' in json_data:
            meeting_name = json_data['fullName']
        elif 'meetingName' in json_data:
            meeting_name = json_data['meetingName']
        elif 'name' in json_data:
            meeting_name = json_data['name']
        
        # Create a safe filename from the meeting name
        safe_meeting_name = ""
        if meeting_name:
            # Replace unsafe characters and spaces with underscores
            import re
            safe_meeting_name = re.sub(r'[^\w\s-]', '', meeting_name)
            safe_meeting_name = re.sub(r'[\s-]+', '_', safe_meeting_name)
        
        # Set default output filename
        output_file = 'opentrack_results.csv'
        
        # Use meeting name in the filename if available
        if safe_meeting_name:
            output_file = f"opentrack_{safe_meeting_name}.csv"
        
        # Override with command line argument if provided
        if len(sys.argv) > 2:
            output_file = sys.argv[2]
        
        parsed_data = parse_opentrack_json(json_data)
        save_to_csv(parsed_data, output_file)
    except Exception as e:
        sys.exit(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
