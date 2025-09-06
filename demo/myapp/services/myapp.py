import pandas as pd
import datetime
import json
from myapp.services.result_service import post  # Import the decorator

def parse_hms_to_duration(hms_string):
    """Convert HH:MM:SS string to datetime.timedelta object"""
    if hms_string == 'Abs':
        return datetime.timedelta(0)
    
    hours, minutes, seconds = map(int, hms_string.split(':'))
    return datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds)

def compute_cumulative(records):
    cumul = {}
    result = []
    for rec in records:
        nom = rec['Nom']
        travail = rec['Travail']

        if travail != 'Abs':
            h, m, s = map(int, travail.split(":"))
            delta = datetime.timedelta(hours=h, minutes=m, seconds=s)
        else:
            delta = datetime.timedelta(0)

        cumul[nom] = cumul.get(nom, datetime.timedelta(0)) + delta

        rec['Travail Cumulée'] = str(cumul[nom])
        result.append(rec)
    return result

@post  # Add this decorator to save results to database
def parse_excel(file_obj) -> pd.DataFrame:
    """
    Parses the Excel file like your original code:
    - Reads columns: 'Entrée.', 'Sortie.', 'Nom.', 'Date.'
    - Computes Travail as delta(Sortie - Entrée)
    - Marks 'Abs' where either is NaT
    - Builds cumulative per person
    - Reorders columns to match your schema
    """
    # Support .xlsx and .xls by letting pandas guess engine
    df = pd.read_excel(file_obj)

    required = ['Entrée.', 'Sortie.', 'Nom.', 'Date.']
    if not all(c in df.columns for c in required):
        raise ValueError("Colonnes requises manquantes: 'Entrée.', 'Sortie.', 'Nom.', 'Date.'")

    extracted = []

    # Normalize and compute row-wise
    for _, row in df.iterrows():
        entree = pd.to_datetime(row['Entrée.'], errors='coerce')
        sortie = pd.to_datetime(row['Sortie.'], errors='coerce')
        nom = row['Nom.']
        date = pd.to_datetime(row['Date.'], format='%d/%m/%Y', errors='coerce')

        if pd.notna(entree) and pd.notna(sortie):
            delta = sortie - entree
            total_seconds = int(delta.total_seconds())
            h = total_seconds // 3600
            m = (total_seconds % 3600) // 60
            s = total_seconds % 60
            travail_str = f"{h:02}:{m:02}:{s:02}"
            extracted.append({
                'Nom': nom,
                'Date': date.date() if pd.notna(date) else None,
                'Entrée': entree.strftime('%H:%M:%S'),
                'Sortie': sortie.strftime('%H:%M:%S'),
                'Travail': travail_str,
            })
        else:
            extracted.append({
                'Nom': nom,
                'Date': date.date() if pd.notna(date) else None,
                'Entrée': 'Abs',
                'Sortie': 'Abs',
                'Travail': 'Abs',
            })

    # Sort by Nom, then Date to make cumulative deterministic
    extracted.sort(key=lambda r: (str(r['Nom']), r['Date'] or pd.Timestamp.min))

    # Compute cumulative
    with_cumul = compute_cumulative(extracted)

    # Reorder cols
    out_df = pd.DataFrame(with_cumul)[
        ['Nom', 'Date', 'Entrée', 'Sortie', 'Travail', 'Travail Cumulée']
    ]
    return out_df