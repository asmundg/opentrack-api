#!/usr/bin/env python3
# filepath: /Volumes/src/priv/opentrack/competitors_by_club.py
import csv
import sys
from collections import defaultdict
from opentrack_utils import load_opentrack_data, get_meeting_name, create_safe_filename, clean_event_name

def parse_competitors_by_club(data):
    """Parse OpenTrack JSON and create a list of competitors by club with their events."""
    
    # Build a dictionary of competitors by bib number
    competitors = {}
    
    for competitor in data['competitors']:
        # Require fields instead of using .get() with fallbacks
        first_name = competitor['firstName']
        last_name = competitor['lastName']
        name = f"{first_name} {last_name}".strip()
        
        # Get club information from teamName field
        club = competitor['teamName']
        category = competitor['category']
        
        # Use sortBib as the key for the competitor dictionary if available
        if 'sortBib' in competitor:
            bib = competitor['sortBib'].lstrip('0')  # Remove leading zeros
            competitors[bib] = {
                'name': name,
                'club': club,
                'category': category,
                'bib': bib,
                'events': set()  # Use set to avoid duplicates
            }
    
    # Process events to find which competitors are in which events
    for event in data['events']:
        event_name = event['name']
        clean_name = clean_event_name(event_name)
        
        # Process units within events
        for unit in event['units']:
            # Process results within units
            for result in unit['results']:
                bib = result['bib']
                if bib in competitors:
                    competitors[bib]['events'].add(clean_name)
    
    # Convert sets to sorted lists and group by club
    club_competitors = defaultdict(list)
    
    for bib, competitor_info in competitors.items():
        # Convert events set to sorted list
        competitor_info['events'] = sorted(list(competitor_info['events']))
        club_competitors[competitor_info['club']].append(competitor_info)
    
    # Sort competitors within each club by bib number
    for club in club_competitors:
        club_competitors[club].sort(key=lambda x: int(x['bib']) if x['bib'].isdigit() else float('inf'))
    
    # Convert to list and sort by club name
    result = []
    for club in sorted(club_competitors.keys()):
        result.extend(club_competitors[club])
    
    return result

def save_competitors_to_csv(data, filename='competitors_by_club.csv'):
    """Save competitors data to CSV."""
    fieldnames = ['Klubb', 'Startnummer', 'Navn', 'Klasse', 'Øvelser']
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for competitor in data:
            # Join events with semicolon separator
            events_str = '; '.join(competitor['events']) if competitor['events'] else ''
            
            writer.writerow({
                'Klubb': competitor['club'],
                'Startnummer': competitor['bib'],
                'Navn': competitor['name'],
                'Klasse': competitor['category'],
                'Øvelser': events_str
            })
    
    print(f"Competitors data saved to {filename}")

def main():
    # Check if argument is provided
    if len(sys.argv) <= 1:
        sys.exit("Please provide either a URL or a local JSON file path.")
    
    input_source = sys.argv[1]
    
    try:
        # Load data using common utility function
        json_data = load_opentrack_data(input_source)
        
        # Generate a filename based on the meeting name
        meeting_name = get_meeting_name(json_data)
        safe_meeting_name = create_safe_filename(meeting_name)
        output_file = f"competitors_by_club_{safe_meeting_name}.csv"
        
        # Override with command line argument if provided
        if len(sys.argv) > 2:
            output_file = sys.argv[2]
        
        # Parse and save data
        competitors_data = parse_competitors_by_club(json_data)
        save_competitors_to_csv(competitors_data, output_file)
        
        # Print summary
        clubs = set(competitor['club'] for competitor in competitors_data)
        print(f"Found {len(competitors_data)} competitors from {len(clubs)} clubs")
        
    except Exception as e:
        sys.exit(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
