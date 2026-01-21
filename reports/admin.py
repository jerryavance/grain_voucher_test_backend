# reports/admin.py
from django.contrib import admin
from .models import ReportExport, ReportSchedule


@admin.register(ReportExport)
class ReportExportAdmin(admin.ModelAdmin):
    list_display = [
        'report_type', 'format', 'status', 'record_count',
        'generated_by', 'requested_at', 'completed_at'
    ]
    list_filter = ['report_type', 'format', 'status', 'requested_at']
    search_fields = ['generated_by__phone_number', 'file_path']
    readonly_fields = [
        'id', 'requested_at', 'completed_at', 'record_count',
        'file_path', 'file_size'
    ]
    date_hierarchy = 'requested_at'
    
    fieldsets = (
        ('Report Info', {
            'fields': ('id', 'report_type', 'format', 'filters')
        }),
        ('Status', {
            'fields': ('status', 'error_message')
        }),
        ('File Info', {
            'fields': ('file_path', 'file_size', 'record_count')
        }),
        ('Metadata', {
            'fields': ('generated_by', 'hub', 'requested_at', 'completed_at', 'expires_at')
        }),
    )


@admin.register(ReportSchedule)
class ReportScheduleAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'report_type', 'frequency', 'is_active',
        'last_run', 'next_run', 'created_by'
    ]
    list_filter = ['report_type', 'frequency', 'is_active', 'created_at']
    search_fields = ['name', 'created_by__phone_number']
    readonly_fields = ['id', 'created_at', 'updated_at', 'last_run']
    filter_horizontal = ['recipients']
    
    fieldsets = (
        ('Schedule Info', {
            'fields': ('id', 'name', 'report_type', 'format', 'is_active')
        }),
        ('Schedule Settings', {
            'fields': (
                'frequency', 'day_of_week', 'day_of_month',
                'time_of_day'
            )
        }),
        ('Filters', {
            'fields': ('filters',)
        }),
        ('Recipients', {
            'fields': ('recipients',)
        }),
        ('Metadata', {
            'fields': (
                'hub', 'created_by', 'created_at', 'updated_at',
                'last_run', 'next_run'
            )
        }),
    )