# myapp/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('dbbi/parse-excel/', views.parse_excel_view, name='parse-excel'),
    path('dbbi/sample-data/', views.sample_data_view, name='sample-data'),
    path('dbbi/all/', views.get_all_dbbi, name='get-all-dbbi'),
    
    path('best-employee/', views.best_employee, name='best_employee'),
    path('worst-employee/', views.worst_employee, name='worst_employee'),
    path('average-hours/', views.average_hours, name='average_hours'),
    path('weekly-trends/', views.weekly_trends, name='weekly_trends'),
    path('all-employees/', views.all_employees_stats, name='all_employees'),
    path('dashboard-summary/', views.dashboard_summary, name='dashboard_summary'),
    path('heures-realisees/', views.heures_realisees, name='heures_realisees'),
    path('heures-restantes/', views.heures_restantes, name='heures_restantes'),
    path('heures-restantes-par-employe/', views.heures_restantes_par_employe, name='heures_restantes_par_employe'),
]



