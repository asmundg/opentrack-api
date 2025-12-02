import csv
import sys
from typing import Any
from opentrack_utils import (
    fetch_json_data, get_meeting_name, clean_event_name, 
    process_local_json, create_safe_filename, load_opentrack_data
)

def parse_opentrack_json(data: dict[str, Any]) -> list[dict[str, Any]]:
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
    
    meeting_name = get_meeting_name(data)
    
    for event in events:
        # Require fields
        event_name = event['name']
        
        # Use utility function to clean event name
        clean_event_name_str = clean_event_name(event_name)
                
        # Process units within events
        for unit in event['units']:
            # Process results within units
            for result in unit['results']:
                # Skip results without athlon points or catpos (but allow 0 points)
                if 'athlonPoints' not in result or 'catpos' not in result:
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
                    'Øvelse': clean_event_name_str,
                    'Stevne': meeting_name,
                    'Tyrvingpoeng': athlon_points
                })
    
    return results

def save_to_csv(data: list[dict[str, Any]], filename: str = 'opentrack_results.csv') -> None:
    """Save parsed data to CSV."""
    fieldnames = ['Startnummer', 'Navn', 'Klubb', 'Klasse', 'Øvelse', 'Stevne', 'Tyrvingpoeng']
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    
    print(f"Data saved to {filename}")

def main() -> None:
    # Check if argument is provided
    if len(sys.argv) <= 1:
        sys.exit("Please provide either a URL or a local JSON file path.")
    
    input_source = sys.argv[1]
    
    # Load data using utility function
    try:
        json_data = load_opentrack_data(input_source)
        meeting_name = get_meeting_name(json_data)
        safe_meeting_name = create_safe_filename(meeting_name)
        output_file = f"tyrvingpoeng_{safe_meeting_name}.csv"
        
        # Override with command line argument if provided
        if len(sys.argv) > 2:
            output_file = sys.argv[2]
        
        parsed_data = parse_opentrack_json(json_data)
        save_to_csv(parsed_data, output_file)
    except Exception as e:
        sys.exit(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
