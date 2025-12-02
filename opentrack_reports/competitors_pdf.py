#!/usr/bin/env python3
# filepath: /Volumes/src/priv/opentrack/competitors_pdf.py
from typing import Any, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_CENTER
import itertools
from collections import defaultdict

def create_pdf_from_competitors(competitors_data: list[dict[str, Any]], output_filename: str, meeting_name: Optional[str] = None) -> None:
    """
    Create a nicely formatted PDF from the competitors data.
    
    Args:
        competitors_data: List of competitor dictionaries from parse_competitors_by_club
        output_filename: Name of the output PDF file
        meeting_name: Name of the competition for the title (optional)
    """
    # Initialize the PDF document
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=A4,
        rightMargin=0.8*cm,
        leftMargin=0.8*cm,
        topMargin=1.2*cm,
        bottomMargin=1.2*cm
    )
    
    # Get current date
    from datetime import datetime
    current_date = datetime.now().strftime("%d %B %Y")
    
    # Initialize styles
    styles = getSampleStyleSheet()
    
    # Create a paragraph style for the events column to enable text wrapping
    events_style = ParagraphStyle(
        name='EventsStyle',
        parent=styles['Normal'],
        fontSize=8,
        leading=9,  # Line spacing
        wordWrap='CJK'  # CJK wrapping provides better handling of long words
    )
    
    # Create a custom style for the title
    title_style = ParagraphStyle(
        name='TitleStyle',
        parent=styles['Heading1'],
        fontSize=11,
        alignment=TA_CENTER,
        spaceAfter=6
    )
    
    # Create a custom style for the club headers
    club_style = ParagraphStyle(
        name='ClubStyle',
        parent=styles['Heading2'],
        fontSize=9,
        spaceAfter=4,
        spaceBefore=8,
        borderWidth=1,
        borderColor=colors.lightblue,
        borderPadding=2,
        borderRadius=2,
        leftIndent=3
    )
    
    # Create a list to hold the elements that will be built into the PDF
    elements = []
    
    # Add the main title
    if meeting_name:
        elements.append(Paragraph(f"Competitors by Club - {meeting_name}", title_style))
    else:
        elements.append(Paragraph("Competitors by Club", title_style))
    
    # Add date
    date_style = ParagraphStyle(
        name='DateStyle',
        parent=styles['Normal'],
        fontSize=7,
        alignment=TA_CENTER,
        spaceAfter=3
    )
    elements.append(Paragraph(f"Generated on {current_date}", date_style))
    elements.append(Spacer(1, 0.2*cm))
    
    # First, preserve the original order which is sorted by bib
    # Make a copy of each competitor with an index to track original order
    indexed_competitors = []
    for i, competitor in enumerate(competitors_data):
        competitor_copy = competitor.copy()
        competitor_copy['_original_index'] = i
        indexed_competitors.append(competitor_copy)
    
    # Group competitors by club while preserving original bib order
    club_competitors = defaultdict(list)
    for competitor in indexed_competitors:
        club_competitors[competitor['club']].append(competitor)
    
    # Process each club in alphabetical order
    for club_name in sorted(club_competitors.keys()):
        # Get competitors for this club
        club_competitors_list = club_competitors[club_name]
        competitor_count = len(club_competitors_list)
        
        # Sort this club's competitors by first name (all parts except the last)
        # With a secondary sort by last name if first names are equal
        club_competitors_list.sort(key=lambda x: (" ".join(x['name'].split()[:-1]) if len(x['name'].split()) > 1 else "", x['name'].split()[-1]))
        
        # Calculate bib list for this club and compress contiguous ranges
        bib_numbers = sorted([int(competitor['bib']) for competitor in club_competitors_list])
        
        def compress_bib_ranges(bibs: list[int]) -> str:
            """Compress a list of bib numbers into ranges like '1-5, 8, 10-12'"""
            if not bibs:
                return ""
            
            ranges = []
            start = bibs[0]
            end = bibs[0]
            
            for i in range(1, len(bibs)):
                if bibs[i] == end + 1:
                    # Contiguous, extend the current range
                    end = bibs[i]
                else:
                    # Gap found, finalize current range
                    if start == end:
                        ranges.append(str(start))
                    else:
                        ranges.append(f"{start}-{end}")
                    start = end = bibs[i]
            
            # Add the final range
            if start == end:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{end}")
            
            return ", ".join(ranges)
        
        bib_range_text = compress_bib_ranges(bib_numbers)
        if len(bib_numbers) == 1:
            bib_label = "bib"
        else:
            bib_label = "bibs"
        
        elements.append(Paragraph(f"{club_name} ({competitor_count} competitor{'s' if competitor_count != 1 else ''}, {bib_label} {bib_range_text})", club_style))
        
        # Create styles for list items
        competitor_name_style = ParagraphStyle(
            name='CompetitorNameStyle',
            parent=styles['Normal'],
            fontSize=7,
            fontName='Helvetica-Bold',
            spaceBefore=3,
            spaceAfter=0
        )
        
        events_style = ParagraphStyle(
            name='EventsStyle',
            parent=styles['Normal'],
            fontSize=6,  # Smaller font for events
            spaceAfter=2,
            leading=8,
            wordWrap='CJK'
        )
        
        # Create a list item for each competitor
        for competitor in club_competitors_list:
            # Format competitor info with name as firstname lastname
            formatted_name = competitor['name']
                
            competitor_info = f"{competitor['bib']} - {formatted_name} ({competitor['category']})"
            
            # Create a paragraph with competitor info in bold and events in smaller font
            if competitor['events']:
                events_list = competitor['events']
                events_str = " • ".join(events_list)
                
                # Use XML formatting to combine different styles in one paragraph
                combined_text = f"{competitor_info}: <font size='6'>{events_str}</font>"
                elements.append(Paragraph(combined_text, competitor_name_style))
            else:
                # Just the competitor info with "No events" in smaller font
                combined_text = f"{competitor_info}: <font size='6'>No events</font>"
                elements.append(Paragraph(combined_text, competitor_name_style))
            
            # Add a light horizontal line between competitors
            elements.append(Spacer(1, 1))
            
            # Add horizontal line
            from reportlab.platypus import HRFlowable
            elements.append(HRFlowable(
                width="100%",
                thickness=0.2,
                color=colors.lightgrey,
                spaceBefore=0,
                spaceAfter=0
            ))
            
            elements.append(Spacer(1, 1))
        elements.append(Spacer(1, 0.2*cm))
    
    # Add a summary section
    summary_style = ParagraphStyle(
        name='SummaryStyle',
        parent=styles['Heading3'],
        fontSize=8,
        spaceAfter=3,
        spaceBefore=6
    )
    normal_style = ParagraphStyle(
        name='NormalText',
        parent=styles['Normal'],
        fontSize=7,
        spaceAfter=2
    )
    
    # Calculate statistics
    total_competitors = len(competitors_data)
    total_clubs = len(club_competitors)
    
    # Find most common events
    all_events = []
    for competitor in competitors_data:
        all_events.extend(competitor['events'])
    
    from collections import Counter
    event_counter = Counter(all_events)
    most_common_events = event_counter.most_common(5)  # Top 5 events
    
    # Add summary section
    elements.append(Paragraph("Summary", summary_style))
    elements.append(Paragraph(f"Total Competitors: {total_competitors}", normal_style))
    elements.append(Paragraph(f"Total Clubs: {total_clubs}", normal_style))
    
    if most_common_events:
        elements.append(Paragraph("Most Popular Events:", normal_style))
        for event, count in most_common_events:
            elements.append(Paragraph(f"• {event}: {count} competitor{'s' if count != 1 else ''}", normal_style))
    
    # Build the PDF with page numbering
    def add_page_number(canvas, doc):
        page_num = canvas.getPageNumber()
        text = f"Page {page_num}"
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(doc.width + doc.rightMargin - 5, doc.bottomMargin - 8, text)
        canvas.restoreState()
    
    # Build the PDF with page numbers
    doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)
    
    print(f"PDF report saved to {output_filename}")

if __name__ == "__main__":
    print("This module is not meant to be run directly. Import it from competitors_by_club.py")
