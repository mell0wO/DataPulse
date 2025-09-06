from django.contrib import admin
from .models import Dbbi, FunctionResult

@admin.register(Dbbi)
class DbbiAdmin(admin.ModelAdmin):
    list_display = ['nom', 'date', 'entree', 'sortie', 'travail', 'travail_cumulee']
    list_filter = ['date', 'nom']
    search_fields = ['nom']
    # date_hierarchy = "date_plain"

@admin.register(FunctionResult)
class FunctionResultAdmin(admin.ModelAdmin):
    list_display = ['function_name', 'success', 'executed_at']
    list_filter = ['success', 'function_name']
    readonly_fields = ['created_at']
    search_fields = ['function_name']