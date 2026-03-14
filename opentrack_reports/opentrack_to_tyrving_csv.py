import csv
from datetime import datetime
from typing import Any

import openpyxl

from .opentrack_utils import clean_event_name, get_meeting_name
from .tyrving_calculator import calc_points


def load_birth_years(xlsx_path: str) -> dict[str, int]:
    """Load name → birth year mapping from participant xlsx.

    The xlsx has columns: Fornavn (A), Etternavn (B), Fødselsdato (F, DD.MM.YYYY).
    """
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.active
    result: dict[str, int] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        first, last, _, _, _, dob = row[:6]
        if not dob or not first or not last:
            continue
        name = f"{first} {last}"
        result[name] = int(str(dob).split(".")[-1])
    wb.close()
    return result


def parse_opentrack_json(
    data: dict[str, Any],
    birth_years: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Parse OpenTrack JSON and extract required fields.

    When OpenTrack returns 0 points (e.g. for 18/19 age groups),
    computes points locally using the Tyrving coefficient table.
    Uses exact age class from birth_years when available.
    """
    results = []

    meeting_year = datetime.strptime(data["date"], "%Y-%m-%d").year
    birth_years = birth_years or {}

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

        # Derive exact age class from birth year when available
        exact_cat = None
        by = birth_years.get(name)
        if by is not None:
            age = meeting_year - by
            exact_cat = f"{category[0]}{age}"

        # Use sortBib as the key for the bib dictionary if available
        if 'sortBib' in competitor:
            bib = competitor['sortBib'].lstrip('0')  # Remove leading zeros
            bib_dict[bib] = {
                'name': name,
                'club': club,
                'category': category,
                'exact_category': exact_cat,
            }

    # Process events
    events = data['events']

    meeting_name = get_meeting_name(data)
    backfilled = 0

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
                performance = result.get('performance', '')

                competitor_info = bib_dict[bib]
                competitor_name = competitor_info['name']
                club_name = competitor_info['club']
                category = competitor_info['category']

                # Backfill missing points using local calculator
                if athlon_points == 0 and performance and performance != 'NM':
                    # Try exact age class first (e.g. G18), fall back to combined (G18/19)
                    exact_cat = competitor_info.get('exact_category')
                    computed = None
                    if exact_cat:
                        computed = calc_points(exact_cat, clean_event_name_str, performance)
                    if computed is None or computed == 0:
                        computed = calc_points(category, clean_event_name_str, performance)
                    if computed is not None and computed > 0:
                        if exact_cat:
                            print(f"  {competitor_name}: using {exact_cat} (exact age class)")
                        athlon_points = computed
                        backfilled += 1

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

    if backfilled > 0:
        print(f"Backfilled {backfilled} missing Tyrving point(s) using local calculator.")

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
