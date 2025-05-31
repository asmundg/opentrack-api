#!/usr/bin/env python3
# filepath: /Volumes/src/priv/opentrack/start_lists.py
import argparse
import json
import sys
import os
import re
import urllib.request
import urllib.error
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime

# Import required functions from local modules - no fallbacks
from opentrack_utils import fetch_json_data, process_local_json

def create_start_lists(data, output_filename=None, event_type=None, events=None, day=None):
    """
    Create start lists PDF for track events with lane assignments.
    
    Args:
        data: JSON dictionary of competitor data from OpenTrack
        output_filename: Name of the output PDF file (optional, will be auto-generated if not provided)
        event_type: Type of track event to filter by (optional)
        events: List of event codes to filter by (optional, overrides event_type)
        day: Day number to filter by (optional, e.g., 1, 2, 3)
    """
    # Require raw JSON format from OpenTrack
    if not isinstance(data, dict) or 'competitors' not in data or 'events' not in data:
        raise TypeError("Data must be a dict with 'competitors' and 'events' keys from OpenTrack JSON")
    
    # Parse competitor data
    from competitors_by_club import parse_competitors_by_club
    competitors_data = parse_competitors_by_club(data)
    
    # Extract meeting name from data - require it to be present
    meeting_name = data['fullName']
    meeting_date = data.get('date', '')
    
    # Parse the meeting date for better formatting
    formatted_meeting_date = meeting_date
    if meeting_date:
        try:
            from datetime import datetime as dt
            parsed_date = dt.strptime(meeting_date, '%Y-%m-%d')
            formatted_meeting_date = parsed_date.strftime('%d %B %Y')
        except ValueError:
            # Keep original format if parsing fails
            formatted_meeting_date = meeting_date
    
    # Filter events to process - track events only
    track_event_codes = ['60', '100', '200', '400', '800', '1500', '3000', '5000', '10000', 
                         '60H', '80H', '100H', '110H', '200H', '400H', '3000SC', 
                         '4x100', '4x200', '4x400', '600']
    events_to_process = []
    
    for event in data['events']:
        event_code = event.get('eventCode', '')
        event_id = event.get('eventId', event_code)
        
        # Check if this is a track event
        is_track_event = any(code in event_code for code in track_event_codes)
        if not is_track_event:
            continue
            
        # Check if we should include this event based on filters
        if events:
            # Filter by specific event codes
            event_list = events if isinstance(events, list) else [events]
            if not any(evt_type in event_code for evt_type in event_list):
                continue
        elif event_type:
            # Filter by single event type
            if event_type not in event_code:
                continue
        
        # Filter by day if specified
        if day is not None:
            event_day = event.get('day', 1)
            if event_day != day:
                continue
        
        events_to_process.append(event)
    
    if not events_to_process:
        available_events = [f"{event.get('eventCode', 'Unknown')} (ID: {event.get('eventId', 'N/A')})" for event in data['events']]
        raise ValueError(f"No matching track events found. Available events: {available_events}")
    
    # Generate output filename if not provided
    if output_filename is None:
        import re
        safe_meeting_name = meeting_name
        if safe_meeting_name:
            # Replace spaces with underscores and remove special characters
            safe_meeting_name = re.sub(r'[^\w\s-]', '', safe_meeting_name)
            safe_meeting_name = re.sub(r'[\s-]+', '_', safe_meeting_name)
            
            day_suffix = f"_day{day}" if day is not None else ""
            
            if len(events_to_process) == 1:
                event_code = events_to_process[0]['eventCode']
                output_filename = f"start_lists_{event_code}_{safe_meeting_name}{day_suffix}.pdf"
            else:
                output_filename = f"start_lists_multiple_{safe_meeting_name}{day_suffix}.pdf"
        else:
            day_suffix = f"_day{day}" if day is not None else ""
            
            if len(events_to_process) == 1:
                event_code = events_to_process[0]['eventCode']
                output_filename = f"start_lists_{event_code}{day_suffix}.pdf"
            else:
                output_filename = f"start_lists_multiple{day_suffix}.pdf"
    
    # Print debug information
    day_filter_text = f" (filtered by day {day})" if day is not None else ""
    print(f"Creating start lists for {len(events_to_process)} events{day_filter_text}:")
    for event in events_to_process:
        event_day = event.get('day', 1)
        print(f"  - {event['eventCode']} (ID: {event.get('eventId', 'N/A')}) - Day {event_day}")
    print(f"Meeting name: {meeting_name}")
    print(f"Output filename: {output_filename}")
    
    # Create a mapping of bib numbers to competitors
    bib_to_competitor = {}
    for competitor in competitors_data:
        if 'bib' in competitor:
            bib_to_competitor[competitor['bib']] = competitor
    
    # Initialize the PDF document in portrait orientation (standard for start lists)
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    # Initialize styles
    styles = getSampleStyleSheet()
    
    # Create custom styles for start lists
    title_style = ParagraphStyle(
        name='TitleStyle',
        parent=styles['Heading1'],
        fontSize=16,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        spaceAfter=8,
        spaceBefore=4
    )
    
    event_title_style = ParagraphStyle(
        name='EventTitleStyle',
        parent=styles['Heading2'],
        fontSize=14,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        spaceAfter=6,
        spaceBefore=12
    )
    
    heat_title_style = ParagraphStyle(
        name='HeatTitleStyle',
        parent=styles['Heading3'],
        fontSize=12,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        spaceAfter=6,
        spaceBefore=8
    )
    
    lane_style = ParagraphStyle(
        name='LaneStyle',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica',
        leading=14,
        leftIndent=10,
        spaceAfter=2
    )
    
    # Create a list to hold the elements that will be built into the PDF
    elements = []
    
    # Group events by type and time to create combined lists
    from collections import defaultdict
    
    # First pass: group events by type and time, collect lane assignments
    event_groups = defaultdict(lambda: {
        'events': [],
        'time': '',
        'all_heats': {},  # heat_id -> list of (lane, bib, competitor_info)
        'heat_names': {}  # heat_id -> heat_name
    })
    
    print("Phase 1: Grouping events by type and time...")
    
    for event in events_to_process:
        event_code = event['eventCode']
        event_id = event.get('eventId', event_code)
        event_name = event.get('name', event_code)
        event_time = event.get('r1Time', '')
        
        # Determine the base event type (e.g., 100, 200, 400)
        base_event_type = None
        track_event_codes = ['100', '200', '400', '800', '1500', '3000', '5000', '10000', '110H', '100H', '400H', '3000SC', '4x100', '4x400']
        for code in track_event_codes:
            if code in event_code:
                base_event_type = code
                break
        
        if not base_event_type:
            print(f"WARNING: Could not determine base event type for {event_code}, skipping")
            continue
        
        # Create group key based on event type and time
        if not event_time:
            print(f"ERROR: Event {event_code} (ID: {event_id}) missing 'r1Time' field, cannot group events without start time")
            continue
        group_key = f"{base_event_type}_{event_time}"
        
        print(f"Processing event: {event_name} ({event_code}, ID: {event_id}) -> Group: {group_key}")
        
        # Add event info to group
        event_groups[group_key]['events'].append({
            'code': event_code,
            'id': event_id,
            'name': event_name,
            'day': event.get('day', 1)
        })
        event_groups[group_key]['time'] = event_time
        if 'day' not in event_groups[group_key]:
            event_groups[group_key]['day'] = event.get('day', 1)
        
        # Extract heat and lane information from units/results
        for unit in event.get('units', []):
            heat_id = unit.get('unitId', 'Heat 1')
            heat_name = unit.get('name', heat_id)
            
            if heat_id not in event_groups[group_key]['all_heats']:
                event_groups[group_key]['all_heats'][heat_id] = []
                event_groups[group_key]['heat_names'][heat_id] = heat_name
            
            for result in unit.get('results', []):
                if 'bib' in result and 'lane' in result:
                    lane = result['lane']
                    bib = result['bib']
                    
                    # Get competitor info
                    competitor_info = bib_to_competitor.get(bib, {
                        'name': 'Unknown',
                        'club': 'Unknown',
                        'category': 'Unknown'
                    })
                    
                    event_groups[group_key]['all_heats'][heat_id].append({
                        'lane': lane,
                        'bib': bib,
                        'competitor': competitor_info,
                        'event_name': event_name
                    })
    
    print(f"Phase 2: Processing {len(event_groups)} event groups...")
    
    # Define the preferred order of track events
    event_type_order = ['60', '100', '200', '400', '600', '800', '1500', '3000', '5000', '10000', 
                        '60H', '80H', '100H', '110H', '200H', '400H', '3000SC', 
                        '4x100', '4x200', '4x400']
    
    def sort_group_key(group_item):
        """Sort groups first by event type order, then by full datetime (day + time)"""
        group_key, group_data = group_item
        base_event_type = group_key.split('_')[0]
        event_time = group_data['time']
        event_day = group_data.get('day', 1)
        
        # Get the order index for the event type, default to 999 if not found
        type_order = event_type_order.index(base_event_type) if base_event_type in event_type_order else 999
        
        # Convert time to minutes since midnight for proper sorting
        try:
            time_parts = event_time.split(':')
            hours = int(time_parts[0])
            minutes = int(time_parts[1])
            minutes_since_midnight = hours * 60 + minutes
        except (ValueError, IndexError):
            minutes_since_midnight = 9999  # Put invalid times at the end
        
        return (type_order, event_day, minutes_since_midnight)
    
    # Process each group and create start lists
    sorted_groups = sorted(event_groups.items(), key=sort_group_key)
    print(f"Groups will be processed in this order:")
    for group_key, group_data in sorted_groups:
        base_event_type = group_key.split('_')[0]
        event_day = group_data.get('day', 1)
        print(f"  {group_key} (Event Type: {base_event_type}, Day: {event_day}, Time: {group_data['time']})")
    
    for group_key, group_data in sorted_groups:
        print(f"\nProcessing group: {group_key}")
        print(f"  Events in group: {[e['code'] for e in group_data['events']]}")
        print(f"  Time: {group_data['time']}")
        print(f"  Total heats: {len(group_data['all_heats'])}")
        
        if len(group_data['all_heats']) == 0:
            print(f"  No heats in group {group_key}, skipping")
            continue
        
        # Create group header using event names
        if len(group_data['events']) > 1:
            event_names = [e['name'] for e in group_data['events']]
            group_header = " / ".join(event_names)
        else:
            group_header = group_data['events'][0]['name']
        
        # Calculate the actual event date by combining base date and event day
        event_date_str = formatted_meeting_date
        if meeting_date and 'day' in group_data:
            try:
                from datetime import datetime as dt, timedelta
                base_date = dt.strptime(meeting_date, '%Y-%m-%d')
                event_date = base_date + timedelta(days=group_data['day'] - 1)
                event_date_str = event_date.strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                event_date_str = formatted_meeting_date
        
        # Add event header
        elements.append(Paragraph(f"{group_header}", event_title_style))
        elements.append(Paragraph(f"{meeting_name} - {event_date_str} - START TIME: {group_data['time']}", lane_style))
        elements.append(Spacer(1, 0.3*cm))
        
        # Sort heats by heat ID/name for consistent ordering
        sorted_heats = sorted(group_data['all_heats'].items(), key=lambda x: x[0])
        
        for heat_id, heat_competitors in sorted_heats:
            heat_name = group_data['heat_names'][heat_id]
            
            if not heat_competitors:
                continue
            
            # Add heat header
            elements.append(Paragraph(f"{heat_name}", heat_title_style))
            
            # Sort competitors by lane number
            sorted_competitors = sorted(heat_competitors, key=lambda x: int(x['lane']) if str(x['lane']).isdigit() else 999)
            
            # Create lane listings
            for competitor_info in sorted_competitors:
                lane = competitor_info['lane']
                bib = competitor_info['bib']
                competitor = competitor_info['competitor']
                
                # Format name (Last, First)
                name_parts = competitor['name'].split()
                if len(name_parts) > 1:
                    last_name = name_parts[-1]
                    first_name = " ".join(name_parts[:-1])
                    formatted_name = f"{last_name.upper()}, {first_name}"
                else:
                    formatted_name = competitor['name'].upper()
                
                # Create lane entry
                lane_text = f"Lane {lane}: {bib} {formatted_name} ({competitor['club']}) - {competitor['category']}"
                elements.append(Paragraph(lane_text, lane_style))
            
            elements.append(Spacer(1, 0.4*cm))
        
        # Add page break between event groups
        elements.append(PageBreak())
    
    # Define a function for page numbers
    def add_page_number(canvas, doc):
        page_num = canvas.getPageNumber()
        text = f"Page {page_num}"
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(doc.width + doc.rightMargin - 10, 10, text)
        canvas.restoreState()
    
    # Build the PDF
    doc.build(elements, 
              onFirstPage=add_page_number,
              onLaterPages=add_page_number)
    
    print(f"Start lists saved to {output_filename}")

def detect_track_event(data):
    """
    Auto-detect a track event from the data.
    
    Args:
        data: JSON dictionary of competitor data
        
    Returns:
        Detected event code or '100' as default if none detected
    """
    # Common track event codes
    track_event_codes = ['60', '100', '200', '400', '800', '1500', '3000', '5000', '10000', 
                         '60H', '80H', '100H', '110H', '200H', '400H', '3000SC', 
                         '4x100', '4x200', '4x400', '600']
    
    # First, try to find events that have units with results
    events_with_competitors = set()
    for event in data.get('events', []):
        event_code = event.get('eventCode', '')
        
        # Check if this is a track event
        is_track_event = False
        for code in track_event_codes:
            if code in event_code:
                is_track_event = True
                break
                
        if is_track_event:
            # Check if there are units with results
            for unit in event.get('units', []):
                if unit.get('results', []):
                    events_with_competitors.add(event_code)
                    print(f"Detected track event with competitors: {event_code}")
                    break
    
    # If we found track events with competitors, return the first one
    if events_with_competitors:
        sorted_events = sorted(events_with_competitors)
        print(f"Auto-detected event type: {sorted_events[0]}")
        return sorted_events[0]
    
    # Fallback: Try to find a suitable track event from the available events
    for event in data.get('events', []):
        event_code = event.get('eventCode', '')
        for code in track_event_codes:
            if code in event_code:
                print(f"Auto-detected event type: {code}")
                return code
    
    # If we don't find any, return 100 as default
    print("No track events detected, using default event type: 100")
    return '100'

def load_data_from_source(source):
    """
    Load data from a source which can be a URL or a local file path.
    
    Args:
        source: URL or file path to the JSON data
        
    Returns:
        Parsed JSON data
    """
    # Determine if source is a URL or a local file
    if source.startswith(('http://', 'https://')):
        return fetch_json_data(source)
    else:
        return process_local_json(source)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate start lists PDF for track events')
    parser.add_argument('source', help='JSON source URL or local file path')
    parser.add_argument('-o', '--output', help='Output PDF filename (optional, will be auto-generated if not provided)')
    parser.add_argument('-e', '--event', help='Event type code (optional, will be auto-detected if not specified)',
                        action='append', dest='events')
    parser.add_argument('--all-events', action='store_true', help='Process all track events found in the data')
    parser.add_argument('-d', '--day', type=int, help='Filter events by day number (e.g., 1, 2, 3)', metavar='N')
    
    args = parser.parse_args()
    
    try:
        # Load data from source
        data = load_data_from_source(args.source)
        
        # Determine which events to process
        events_to_process = None
        
        if args.all_events:
            # Process all track events
            track_event_codes = ['60', '100', '200', '400', '800', '1500', '3000', '5000', '10000', 
                                 '60H', '80H', '100H', '110H', '200H', '400H', '3000SC', 
                                 '4x100', '4x200', '4x400', '600']
            events_to_process = []
            
            if isinstance(data, dict) and 'events' in data:
                for event in data['events']:
                    event_code = event.get('eventCode', '')
                    for code in track_event_codes:
                        if code in event_code and event_code not in events_to_process:
                            events_to_process.append(event_code)
                            break
            
            if not events_to_process:
                print("No track events found in the data")
                sys.exit(1)
        elif args.events:
            # Use the events specified in the arguments
            events_to_process = args.events
        
        # Create the start lists PDF
        create_start_lists(
            data, 
            output_filename=args.output, 
            events=events_to_process,
            day=args.day
        )
        
        print(f"Start lists successfully generated")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
