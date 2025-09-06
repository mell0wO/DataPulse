from django.shortcuts import render
from collections import defaultdict
from datetime import timedelta
import datetime  
from django.db import connection
from django.db import transaction
from django.utils.dateparse import parse_date
from rest_framework import status, views, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
import pandas as pd
from io import BytesIO
import tempfile
import os
from myapp.models import Dbbi  # Import Dbbi here instead
from myapp.services.result_service import post

from .models import Dbbi
from .serializers import DbbiSerializer


@post
def save_to_database(data):
    """
    Save parsed data to Dbbi model
    """
    saved_count = 0
    
    for record in data:
        try:
            # Create or update record
            dbbi_obj, created = Dbbi.objects.get_or_create(
                nom=record['Nom'],
                date=record['Date'],
                defaults={
                    'entree': record['Entrée'],
                    'sortie': record['Sortie'],
                    'travail': record['Travail'],
                    'travail_cumulee': record['Travail Cumulée']
                }
            )
            
            if created:
                saved_count += 1
                
        except Exception as e:
            print(f"Error saving record {record}: {e}")
            continue
    return saved_count

# Move your parsing functions here or import them correctly
def parse_hms_to_duration(hms_string):
    """
    Convert HH:MM:SS string to datetime.timedelta object
    """
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

def parse_excel(file_obj):
    """
    Parses the Excel file like your original code:
    - Reads columns: 'Entrée.', 'Sortie.', 'Nom.', 'Date.'
    - Computes Travail as delta(Sortie - Entrée)
    - Marks 'Abs' where either is NaT
    - Builds cumulative per person
    - Reorders columns to match your schema
    """
    try:
        # Get file name to determine extension
        file_name = getattr(file_obj, 'name', '').lower()
        
        # Specify engine based on file extension
        if file_name.endswith('.xlsx'):
            engine = 'openpyxl'
        elif file_name.endswith('.xls'):
            engine = 'xlrd'
        else:
            # For unknown extensions, try both engines
            engine = None
            
        print(f"Reading file: {file_name} with engine: {engine}")
        
        # Read the Excel file
        if engine:
            df = pd.read_excel(file_obj, engine=engine)
        else:
            # Try both engines for unknown file types
            try:
                file_obj.seek(0)
                df = pd.read_excel(file_obj, engine='openpyxl')
                print("Successfully read with openpyxl engine")
            except:
                file_obj.seek(0)
                df = pd.read_excel(file_obj, engine='xlrd')
                print("Successfully read with xlrd engine")
            
    except Exception as e:
        print(f"Error reading Excel file: {str(e)}")
        raise ValueError(f"Cannot read Excel file. Please ensure it's a valid Excel file (.xls or .xlsx). Error: {str(e)}")
    
    required = ['Entrée.', 'Sortie.', 'Nom.', 'Date.']
    if not all(c in df.columns for c in required):
        available_columns = df.columns.tolist()
        print(f"Required columns: {required}")
        print(f"Available columns: {available_columns}")
        raise ValueError(f"Colonnes requises manquantes. Requises: {required}. Disponibles: {available_columns}")

    extracted = []

    # Normalize and compute row-wise
    for index, row in df.iterrows():
        try:
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
                    'Entrée': entree.strftime('%H:%M:%S') if pd.notna(entree) else 'Abs',
                    'Sortie': sortie.strftime('%H:%M:%S') if pd.notna(sortie) else 'Abs',
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
        except Exception as e:
            print(f"Error processing row {index}: {e}")
            print(f"Row data: {row}")
            raise e

    # Sort by Nom, then Date to make cumulative deterministic
    extracted.sort(key=lambda r: (str(r['Nom']), r['Date'] or pd.Timestamp.min))

    # Compute cumulative
    with_cumul = compute_cumulative(extracted)

    # Reorder cols
    out_df = pd.DataFrame(with_cumul)[
        ['Nom', 'Date', 'Entrée', 'Sortie', 'Travail', 'Travail Cumulée']
    ]
    
    print(f"Successfully parsed {len(out_df)} records")
    return out_df

# ViewSet for Dbbi model
class DbbiViewSet(viewsets.ModelViewSet):
    queryset = Dbbi.objects.all()
    serializer_class = DbbiSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        nom = self.request.query_params.get('nom')
        start = self.request.query_params.get('start')
        if nom:
            qs = qs.filter(nom__icontains=nom)
        if start:
            qs = qs.filter(created_at__gte=parse_date(start))
        return qs

@api_view(['POST'])
def parse_excel_view(request):
    """Standalone view for parsing Excel"""
    if 'file' not in request.FILES:
        return Response(
            {'error': 'No file provided'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    file_obj = request.FILES['file']
    
    # Check if file is Excel format
    if not file_obj.name.endswith(('.xlsx', '.xls')):
        return Response(
            {'error': 'File must be in Excel format (.xlsx or .xls)'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Parse the Excel file
        df = parse_excel(file_obj)
        
        # Convert DataFrame to list of dictionaries for JSON response
        result_data = df.to_dict('records')
        saved_count = save_to_database(result_data)
        
        return Response({
            'message': 'File parsed successfully',
            'data': result_data,
            'total_records': len(result_data),
            'saved_records': saved_count
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        # Add detailed error information
        import traceback
        error_details = traceback.format_exc()
        
        return Response({
            'error': f'Error parsing file: {str(e)}',
            'details': error_details,
            'file_name': file_obj.name,
            'file_size': file_obj.size
        }, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['GET'])
def get_all_dbbi(request):
    records = Dbbi.objects.all()
    serializer = DbbiSerializer(records, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def sample_data_view(request):
    """Standalone view for sample data"""
    sample = {
        "columns": ["Nom", "Date", "Entrée", "Sortie", "Travail", "Travail Cumulée"],
        "sample_record": {
            "Nom": "Yasmin Mrabet",
            "Date": "2023-12-01",
            "Entrée": "08:00:00",
            "Sortie": "17:00:00",
            "Travail": "09:00:00",
            "Travail Cumulée": "09:00:00"
        }
    }
    return Response(sample, status=status.HTTP_200_OK)

# =============================================================================
# KPI VIEWS FOR DASHBOARD
# =============================================================================

from collections import defaultdict
from datetime import timedelta
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Dbbi

def parse_hms_to_duration(time_str):
    """Parse time string in HH:MM:SS or HH:MM format to timedelta"""
    try:
        # Split the time string by colons
        parts = time_str.split(':')
        
        if len(parts) == 3:  # HH:MM:SS format
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
        elif len(parts) == 2:  # HH:MM format
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = 0
        else:
            return timedelta(0)
            
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)
    except (ValueError, TypeError):
        return timedelta(0)

@api_view(['GET'])
def best_employee(request):
    """Get the employee with the most hours worked"""
    try:
        totals = defaultdict(timedelta)

        for row in Dbbi.objects.all():
            if row.travail and row.travail != "Abs":
                totals[row.nom] += parse_hms_to_duration(row.travail)

        if not totals:
            return Response({'nom': 'No data', 'total_hours': '00:00'})

        # find employee with max hours
        best_nom, best_total = max(totals.items(), key=lambda x: x[1])

        # format timedelta as HH:MM
        total_seconds = int(best_total.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        total_hours = f"{hours:02}:{minutes:02}"

        return Response({'nom': best_nom, 'total_hours': total_hours})

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    
@api_view(['GET'])
def worst_employee(request):
    """Get the employee with the least hours worked"""
    try:
        totals = defaultdict(timedelta)

        for row in Dbbi.objects.all():
            if row.travail and row.travail != "Abs":
                totals[row.nom] += parse_hms_to_duration(row.travail)

        if not totals:
            return Response({'nom': 'No data', 'total_hours': '00:00'})

        # find employee with minimum hours (excluding zero hours)
        # First, filter out employees with some hours worked
        employees_with_hours = {nom: total for nom, total in totals.items() if total > timedelta(0)}
        
        if not employees_with_hours:
            return Response({'nom': 'No employees with hours worked', 'total_hours': '00:00'})

        # find the employee with the least hours
        worst_nom, worst_total = min(employees_with_hours.items(), key=lambda x: x[1])

        # format timedelta as HH:MM
        total_seconds = int(worst_total.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        total_hours = f"{hours:02}:{minutes:02}"

        return Response({'nom': worst_nom, 'total_hours': total_hours})

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@api_view(['GET'])
def average_hours(request):
    """Get average hours statistics (Python aggregation, works with encrypted fields)."""
    try:
        total = timedelta()
        count = 0

        for row in Dbbi.objects.all():
            if row.travail and row.travail != "Abs":
                total += parse_hms_to_duration(row.travail)
                count += 1

        # Calculate total realized hours
        total_seconds = int(total.total_seconds())  # Use total_seconds() instead of seconds
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        total_realized = f"{hours:02}:{minutes:02}"

        # Average hours (in decimal format like SQL '99.99')
        avg_hours = round(total.total_seconds() / 3600 / count, 2) if count > 0 else 0.0

        data = {
            'total_realized': total_realized,
            'avg_hours': f"{avg_hours:.2f}",
            'remaining_hours': '40:00',  # TODO: replace with your real business logic
            'total_entries_processed': count
        }
        return Response(data)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def weekly_trends(request):
    """Get hours worked by day of week"""
    try:
        # Dictionary to sum hours per day
        trends_dict = defaultdict(float)
        day_map = {'Mon':'Lun','Tue':'Mar','Wed':'Mer','Thu':'Jeu','Fri':'Ven','Sat':'Sam','Sun':'Dim'}

        all_records = Dbbi.objects.all()
        print(f"Total records: {all_records.count()}")  # Debug: check total records

        # Loop through records and aggregate
        for i, rec in enumerate(all_records):
            print(f"Record {i}: date={rec.date}, travail={rec.travail}")  # Debug each record
            
            if rec.travail and rec.travail != 'Abs' and rec.travail != '':
                try:
                    # Handle different time formats
                    if ':' in rec.travail:
                        # Convert HH:MM or HH:MM:SS string to hours float
                        time_parts = rec.travail.split(':')
                        h = int(time_parts[0])
                        m = int(time_parts[1])
                        hours = h + m/60
                        print(f"  Parsed: {h}h {m}m = {hours} hours")  # Debug parsing
                    else:
                        # Try to parse other formats if needed
                        hours = 0
                except (ValueError, AttributeError) as e:
                    print(f"  Error parsing travail '{rec.travail}': {e}")  # Debug parsing errors
                    hours = 0
            else:
                hours = 0
                print(f"  Skipped (Abs or empty)")  # Debug skipped records

            if rec.date:
                day_name = rec.date.strftime('%a')
                day_name = day_map.get(day_name, day_name)
                trends_dict[day_name] += hours
                print(f"  Added {hours} hours to {day_name}")  # Debug aggregation
            else:
                trends_dict['Unknown'] += hours
                print(f"  Added {hours} hours to Unknown (no date)")

        print(f"Trends dict: {dict(trends_dict)}")  # Debug final aggregation

        # Format results as HH:MM
        trends = []
        for day, total in trends_dict.items():
            h = int(total)
            m = int(round((total - h) * 60))
            trends.append({'day_name': day, 'total_hours': f"{h:02}:{m:02}"})
            print(f"Formatted: {day} -> {total} hours -> {h:02}:{m:02}")  # Debug formatting

        # Sort by weekdays
        order = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim']
        known_days = [t for t in trends if t['day_name'] in order]
        unknown_days = [t for t in trends if t['day_name'] not in order]
        
        known_days.sort(key=lambda x: order.index(x['day_name']))
        trends = known_days + unknown_days

        return Response({'trends': trends})
    
    except Exception as e:
        print(f"Exception: {e}")  # Debug any exceptions
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def all_employees_stats(request):
    """Get all employees with their total hours"""
    try:
        employee_hours = defaultdict(float)  # store hours as float

        all_records = Dbbi.objects.all()

        for rec in all_records:
            if rec.travail and rec.travail != 'Abs' and rec.travail.strip() != '':
                try:
                    # Convert HH:MM (or HH:MM:SS) to hours float
                    parts = rec.travail.split(':')
                    if len(parts) >= 2:
                        h = int(parts[0])
                        m = int(parts[1])
                        hours = h + m/60
                    else:
                        hours = 0
                except (ValueError, AttributeError):
                    hours = 0
            else:
                hours = 0

            employee_hours[rec.nom] += hours

        # Format as HH:MM and sort descending by total hours
        employees = []
        for nom, total in sorted(employee_hours.items(), key=lambda x: x[1], reverse=True):
            h = int(total)
            m = int(round((total - h) * 60))  # Added round() for better accuracy
            employees.append({'nom': nom, 'total_hours': f"{h:02}:{m:02}"})

        return Response({'employees': employees})

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from collections import defaultdict
from myapp.models import Dbbi
from datetime import timedelta

def _convert_to_hours(travail_value):
    """Convert travail string to hours float"""
    if not travail_value or travail_value == 'Abs' or travail_value.strip() == '':
        return 0.0
    
    try:
        parts = travail_value.split(':')
        if len(parts) >= 2:
            h = int(parts[0])
            m = int(parts[1])
            return h + m/60
        return 0.0
    except (ValueError, AttributeError):
        return 0.0

def _format_hours(total_hours):
    """Format hours float to HH:MM string"""
    h = int(total_hours)
    m = int(round((total_hours - h) * 60))
    return f"{h:02}:{m:02}"

@api_view(['GET'])
def dashboard_summary(request):
    """Get all dashboard KPIs in one endpoint"""
    try:
        employee_hours = defaultdict(float)
        weekly_hours = defaultdict(float)
        day_map = {'Mon': 'Lun', 'Tue': 'Mar', 'Wed': 'Mer', 'Thu': 'Jeu', 'Fri': 'Ven', 'Sat': 'Sam', 'Sun': 'Dim'}

        all_records = Dbbi.objects.all()

        for rec in all_records:
            hours = _convert_to_hours(rec.travail)
            employee_hours[rec.nom] += hours

            # Weekly trends - only if date exists
            if rec.date:
                day_name = rec.date.strftime('%a')
                day_name_fr = day_map.get(day_name, day_name)
                weekly_hours[day_name_fr] += hours

        # Best and worst employees (excluding zeros)
        employees_with_hours = {nom: hours for nom, hours in employee_hours.items() if hours > 0}
        
        if employees_with_hours:
            best_nom, best_total = max(employees_with_hours.items(), key=lambda x: x[1])
            worst_nom, worst_total = min(employees_with_hours.items(), key=lambda x: x[1])
            best_employee_data = {'nom': best_nom, 'total_hours': _format_hours(best_total)}
            worst_employee_data = {'nom': worst_nom, 'total_hours': _format_hours(worst_total)}
        else:
            best_employee_data = {'nom': 'No data', 'total_hours': '00:00'}
            worst_employee_data = {'nom': 'No data', 'total_hours': '00:00'}

        # Weekly trends formatting - ensure all days are present
        trends = []
        day_order = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
        
        # Add days with hours
        for day_name, hours in weekly_hours.items():
            trends.append({'day_name': day_name, 'total_hours': _format_hours(hours)})
        
        # Add missing days with zero hours
        for day_name in day_order:
            if not any(t['day_name'] == day_name for t in trends):
                trends.append({'day_name': day_name, 'total_hours': '00:00'})
        
        # Sort by day order
        trends.sort(key=lambda x: day_order.index(x['day_name']) if x['day_name'] in day_order else 999)

        # Total realized hours
        total_realized = sum(employee_hours.values())
        total_realized_fmt = _format_hours(total_realized)

        # Additional stats
        total_employees = len(employee_hours)
        employees_with_work = len(employees_with_hours)
        avg_hours = total_realized / employees_with_work if employees_with_work > 0 else 0

        data = {
            'best_employee': best_employee_data,
            'worst_employee': worst_employee_data,
            'weekly_trends': trends,
            'total_realized': total_realized_fmt,
            'remaining_hours': '40:00',
            'stats': {
                'total_employees': total_employees,
                'employees_with_work': employees_with_work,
                'average_hours': round(avg_hours, 2)
            }
        }

        return Response(data)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _convert_to_seconds(travail):
    """Convert HH:MM or HH:MM:SS string to seconds"""
    if not travail or travail == 'Abs' or travail.strip() == '':
        return 0
    try:
        parts = list(map(int, travail.split(':')))
        if len(parts) >= 2:
            return parts[0]*3600 + parts[1]*60 + (parts[2] if len(parts) >= 3 else 0)
        return 0
    except (ValueError, TypeError):
        return 0

def _format_hms(seconds):
    """Format seconds to HH:MM:SS string"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"

def _format_hm(seconds):
    """Format seconds to HH:MM string (without seconds)"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h:02}:{m:02}"

@api_view(['GET'])
def heures_realisees(request):
    """Total hours worked by all employees"""
    try:
        total_seconds = 0
        for rec in Dbbi.objects.all():
            total_seconds += _convert_to_seconds(rec.travail)
        
        return Response({
            'heures_realisees': _format_hm(total_seconds),  # Use HH:MM format
            'heures_realisees_detailed': _format_hms(total_seconds),  # HH:MM:SS for detailed view
            'total_seconds': total_seconds,
            'description': 'Total des heures travaillées par tous les employés'
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def heures_restantes(request):
    """Remaining hours based on expected work (8h per record)"""
    try:
        all_records = Dbbi.objects.exclude(travail='Abs').exclude(travail__isnull=True).exclude(travail='')
        total_seconds = 0
        for rec in all_records:
            total_seconds += _convert_to_seconds(rec.travail)
        
        total_records = all_records.count()
        expected_seconds = total_records * 8 * 3600
        remaining_seconds = max(0, expected_seconds - total_seconds)

        return Response({
            'travail_attendu': _format_hm(expected_seconds),
            'heures_realisees': _format_hm(total_seconds),
            'heures_restantes': _format_hm(remaining_seconds),
            'nombre_jours_travailles': total_records,
            'description': f'Travail attendu: {total_records} jours × 8 heures = {_format_hm(expected_seconds)}'
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def heures_restantes_par_employe(request):
    """Remaining hours per employee"""
    try:
        employees = defaultdict(lambda: {'jours_travailles': 0, 'heures_realisees_seconds': 0})
        
        # Get only records where work was done
        records = Dbbi.objects.exclude(travail='Abs').exclude(travail__isnull=True).exclude(travail='')
        
        for rec in records:
            employees[rec.nom]['jours_travailles'] += 1
            employees[rec.nom]['heures_realisees_seconds'] += _convert_to_seconds(rec.travail)

        result = []
        for nom, data in employees.items():
            expected_seconds = data['jours_travailles'] * 8 * 3600
            remaining_seconds = max(0, expected_seconds - data['heures_realisees_seconds'])
            
            result.append({
                'nom': nom,
                'jours_travailles': data['jours_travailles'],
                'heures_realisees': _format_hm(data['heures_realisees_seconds']),
                'travail_attendu': _format_hm(expected_seconds),
                'heures_restantes': _format_hm(remaining_seconds),
                'deficit_heures': remaining_seconds > 0
            })

        # Sort by remaining hours (most deficit first)
        result.sort(key=lambda x: x['heures_restantes'], reverse=True)

        return Response({'employees': result})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def stats_completes(request):
    """Complete statistics including all metrics"""
    try:
        # Get all data in one query
        records = Dbbi.objects.all()
        
        total_seconds_all = 0
        employees = defaultdict(lambda: {'jours_travailles': 0, 'heures_realisees_seconds': 0})
        jours_avec_travail = 0
        
        for rec in records:
            seconds = _convert_to_seconds(rec.travail)
            total_seconds_all += seconds
            
            if rec.travail and rec.travail != 'Abs' and rec.travail.strip() != '':
                jours_avec_travail += 1
                employees[rec.nom]['jours_travailles'] += 1
                employees[rec.nom]['heures_realisees_seconds'] += seconds

        # Calculate metrics
        expected_seconds_total = jours_avec_travail * 8 * 3600
        remaining_seconds_total = max(0, expected_seconds_total - total_seconds_all)
        
        # Employee stats
        employee_stats = []
        for nom, data in employees.items():
            expected_seconds = data['jours_travailles'] * 8 * 3600
            remaining_seconds = max(0, expected_seconds - data['heures_realisees_seconds'])
            
            employee_stats.append({
                'nom': nom,
                'jours_travailles': data['jours_travailles'],
                'heures_realisees': _format_hm(data['heures_realisees_seconds']),
                'travail_attendu': _format_hm(expected_seconds),
                'heures_restantes': _format_hm(remaining_seconds),
                'deficit': remaining_seconds > 0
            })

        employee_stats.sort(key=lambda x: x['heures_restantes'], reverse=True)

        return Response({
            'global': {
                'total_heures_realisees': _format_hm(total_seconds_all),
                'jours_avec_travail': jours_avec_travail,
                'travail_attendu_total': _format_hm(expected_seconds_total),
                'heures_restantes_total': _format_hm(remaining_seconds_total),
                'taux_realisation': f"{(total_seconds_all / expected_seconds_total * 100):.1f}%" if expected_seconds_total > 0 else "0%"
            },
            'par_employe': employee_stats,
            'total_records': records.count()
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)