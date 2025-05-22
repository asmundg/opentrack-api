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
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        sys.exit(1)

def parse_opentrack_json(data):
    """Parse OpenTrack JSON and extract required fields."""
    results = []
    
    # Build a dictionary of competitors for lookup by competitorId and bib
    competitor_dict = {}
    bib_to_name = {}
    club_dict = {}
    
    for competitor in data.get('competitors', []):
        competitor_id = competitor.get('competitorId', '')
        first_name = competitor.get('firstName', '')
        last_name = competitor.get('lastName', '')
        name = f"{first_name} {last_name}".strip()
        
        # Get club information from teamName field
        club = competitor.get('teamName', '')
        
        competitor_dict[competitor_id] = {'name': name, 'club': club}
        
        # Also store by bib if we can find it (assuming bib is stored somewhere)
        if 'sortBib' in competitor:
            bib = competitor.get('sortBib', '').lstrip('0')  # Remove leading zeros
            bib_to_name[bib] = {'name': name, 'club': club}
    
    # Process events
    events = data.get('events', [])
    
    # Get competition/meeting name from the top level data if available
    meeting_name = data.get('meetingName', '') or data.get('name', '')
    
    for event in events:
        event_name = event.get('name', '')
        event_category = event.get('category', '')
        
        # Process units within events
        for unit in event.get('units', []):
            # Process results within units
            for result in unit.get('results', []):
                bib = result.get('bib', '')
                athlon_points = result.get('athlonPoints', '')
                
                # Try to find competitor info using different available fields
                competitor_name = None
                club_name = ""
                category = ""
                
                # First try the _cptrId if it exists (maps to competitorId)
                if '_cptrId' in result:
                    cptr_id = result.get('_cptrId', '')
                    if cptr_id in competitor_dict:
                        competitor_info = competitor_dict[cptr_id]
                        competitor_name = competitor_info['name']
                        club_name = competitor_info['club']
                        
                        # Try to get category from the competitor's data directly if possible
                        for competitor in data.get('competitors', []):
                            if competitor.get('competitorId', '') == cptr_id:
                                category = competitor.get('category', event_category)
                                break
                
                # If that didn't work, try the bib number
                if not competitor_name and bib in bib_to_name:
                    competitor_info = bib_to_name[bib]
                    competitor_name = competitor_info['name']
                    club_name = competitor_info['club']
                    
                    # Try to find category for this bib number
                    if not category:
                        for competitor in data.get('competitors', []):
                            if competitor.get('sortBib', '').lstrip('0') == bib:
                                category = competitor.get('category', event_category)
                                break
                
                # If we still don't have a name, use the bib number
                if not competitor_name:
                    competitor_name = f"Bib #{bib}"
                
                # If we still don't have a category, use the event category
                if not category:
                    category = event_category
                
                # Add to results list
                results.append({
                    'Startnummer': bib,
                    'Navn': competitor_name,
                    'Klubb': club_name,
                    'Klasse': category,
                    'Øvelse': event_name,
                    'Stevne': meeting_name,
                    'Tyrvingpoeng': athlon_points
                })
    
    return results

def save_to_csv(data, filename='opentrack_results.csv'):
    """Save parsed data to CSV."""
    if not data:
        print("No data to save.")
        return
    
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
            return json.load(f)
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        sys.exit(1)

def main():
    # Check if argument is provided
    if len(sys.argv) <= 1:
        print("Please provide either a URL or a local JSON file path.")
        sys.exit(1)
    
    input_source = sys.argv[1]
    
    # Optional output filename
    output_file = 'opentrack_results.csv'
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    
    # Determine if input is a local file or URL
    if input_source.startswith('http://') or input_source.startswith('https://'):
        json_data = fetch_json_data(input_source)
    else:
        json_data = process_local_json(input_source)
    
    parsed_data = parse_opentrack_json(json_data)
    save_to_csv(parsed_data, output_file)

if __name__ == "__main__":
    main()
