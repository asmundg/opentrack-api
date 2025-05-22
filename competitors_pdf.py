#!/usr/bin/env python3
# filepath: /Volumes/src/priv/opentrack/competitors_pdf.py
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER
import itertools
from collections import defaultdict

def create_pdf_from_competitors(competitors_data, output_filename, meeting_name=None):
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
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
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
        fontSize=10,
        leading=12,  # Line spacing
        wordWrap='CJK'  # CJK wrapping provides better handling of long words
    )
    
    # Create a custom style for the title
    title_style = ParagraphStyle(
        name='TitleStyle',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=12
    )
    
    # Create a custom style for the club headers
    club_style = ParagraphStyle(
        name='ClubStyle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=6,
        spaceBefore=12
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
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=6
    )
    elements.append(Paragraph(f"Generated on {current_date}", date_style))
    elements.append(Spacer(1, 0.5*cm))
    
    # Group competitors by club
    club_competitors = defaultdict(list)
    for competitor in competitors_data:
        club_competitors[competitor['club']].append(competitor)
    
    # Alternate row colors
    rowcolors = (colors.whitesmoke, colors.white)
    
    # Process each club
    for club_name in sorted(club_competitors.keys()):
        # Get competitors for this club
        club_competitors_list = club_competitors[club_name]
        competitor_count = len(club_competitors_list)
        
        # Add club header with competitor count
        elements.append(Paragraph(f"{club_name} ({competitor_count} competitor{'s' if competitor_count != 1 else ''})", club_style))
        
        # Create the table data
        table_data = [['Bib', 'Name', 'Category', 'Events']]
        
        # Sort competitors within the club by bib number
        club_competitors[club_name].sort(key=lambda x: int(x['bib']) if x['bib'].isdigit() else float('inf'))
        
        # Add competitors to the table
        for competitor in club_competitors[club_name]:
            if competitor['events']:
                # Format events with bullet points for better readability
                events_list = competitor['events']
                events_str = " • ".join(events_list)  # Using bullet separator instead of semicolon
            else:
                events_str = ""
                
            # Wrap events text in a Paragraph to enable text wrapping
            events_paragraph = Paragraph(events_str, events_style)
            
            table_data.append([
                competitor['bib'],
                competitor['name'],
                competitor['category'],
                events_paragraph
            ])
        
        # Calculate available width for the table
        available_width = doc.width
        
        # Define column widths as a percentage of available width
        col_widths = [
            available_width * 0.10,  # Bib (10%)
            available_width * 0.35,  # Name (35%)
            available_width * 0.15,  # Category (15%)
            available_width * 0.40   # Events (40%)
        ]
        
        # Create the table with fixed column widths
        table = Table(table_data, repeatRows=1, colWidths=col_widths)
        
        # Create the style for the table
        table_style = TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TOPPADDING', (0, 0), (-1, 0), 12),
            
            # Cell styling
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),  # Align to top for better text wrapping
            
            # Column-specific styling
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Bib numbers centered
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),  # Category centered
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Names left-aligned
            ('ALIGN', (3, 1), (3, -1), 'LEFT'),    # Events left-aligned
            
            # Padding for all cells
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ])
        
        # Add alternating row colors
        for i, row in enumerate(table_data[1:], 1):
            table_style.add('BACKGROUND', (0, i), (-1, i), rowcolors[i % 2])
        
        # Apply the style to the table
        table.setStyle(table_style)
        
        # Add the table to the elements
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
    
    # Add a summary section
    summary_style = ParagraphStyle(
        name='SummaryStyle',
        parent=styles['Heading3'],
        fontSize=12,
        spaceAfter=6,
        spaceBefore=12
    )
    normal_style = ParagraphStyle(
        name='NormalText',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6
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
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(doc.width + doc.rightMargin - 6, doc.bottomMargin - 10, text)
        canvas.restoreState()
    
    # Build the PDF with page numbers
    doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)
    
    print(f"PDF report saved to {output_filename}")

if __name__ == "__main__":
    print("This module is not meant to be run directly. Import it from competitors_by_club.py")
