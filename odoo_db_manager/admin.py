"""
تسجيل النماذج في واجهة الإدارة
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Database, Backup
from .google_sync import GoogleSyncConfig, GoogleSyncLog
from .google_sync_advanced import GoogleSheetMapping, GoogleSyncTask, GoogleSyncConflict, GoogleSyncSchedule
from . import admin_advanced_sync

@admin.register(Database)
class DatabaseAdmin(admin.ModelAdmin):
    """إدارة قواعد البيانات"""

    list_display = ('name', 'db_type', 'is_active', 'created_at')
    list_filter = ('db_type', 'is_active')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'db_type', 'is_active')
        }),
        (_('معلومات الاتصال'), {
            'fields': ('connection_info',),
            'classes': ('collapse',)
        }),
        (_('معلومات النظام'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(Backup)
class BackupAdmin(admin.ModelAdmin):
    """إدارة النسخ الاحتياطية"""

    list_display = ('name', 'database', 'size_display', 'created_at', 'created_by')
    list_filter = ('database', 'created_at')
    search_fields = ('name', 'database__name')
    readonly_fields = ('size', 'created_at', 'created_by')
    fieldsets = (
        (None, {
            'fields': ('name', 'database', 'file_path')
        }),
        (_('معلومات النظام'), {
            'fields': ('size', 'created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(GoogleSyncConfig)
class GoogleSyncConfigAdmin(admin.ModelAdmin):
    """إدارة إعدادات مزامنة غوغل"""

    list_display = ('name', 'is_active', 'last_sync', 'sync_frequency', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('last_sync', 'created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'spreadsheet_id', 'credentials_file', 'is_active', 'sync_frequency')
        }),
        (_('خيارات المزامنة'), {
            'fields': ('sync_databases', 'sync_users', 'sync_customers', 'sync_orders', 'sync_products', 'sync_settings'),
            'classes': ('collapse',)
        }),
        (_('معلومات النظام'), {
            'fields': ('last_sync', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(GoogleSyncLog)
class GoogleSyncLogAdmin(admin.ModelAdmin):
    """إدارة سجلات مزامنة غوغل"""

    list_display = ('config', 'status', 'message', 'created_at')
    list_filter = ('status', 'created_at', 'config')
    search_fields = ('message',)
    readonly_fields = ('config', 'status', 'message', 'details', 'created_at')
    fieldsets = (
        (None, {
            'fields': ('config', 'status', 'message')
        }),
        (_('التفاصيل'), {
            'fields': ('details',),
            'classes': ('collapse',)
        }),
        (_('معلومات النظام'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(GoogleSheetMapping)
class GoogleSheetMappingAdmin(admin.ModelAdmin):
    """إدارة إعدادات مزامنة جوجل شيت"""

    list_display = ('name', 'sheet_name', 'spreadsheet_id', 'is_active', 'last_sync', 'created_at')
    search_fields = ('name', 'sheet_name', 'spreadsheet_id')
    list_filter = ('is_active',)
    readonly_fields = ('created_at', 'updated_at', 'last_sync', 'last_row_processed')

@admin.register(GoogleSyncTask)
class GoogleSyncTaskAdmin(admin.ModelAdmin):
    """إدارة مهام مزامنة غوغل"""

    list_display = ('id', 'mapping', 'task_type', 'status', 'started_at', 'completed_at', 'created_by')
    list_filter = ('status', 'task_type', 'created_at')
    search_fields = ('mapping__name',)
    readonly_fields = ('results', 'error_message', 'error_details', 'created_at', 'started_at', 'completed_at')

@admin.register(GoogleSyncConflict)
class GoogleSyncConflictAdmin(admin.ModelAdmin):
    """إدارة تعارضات مزامنة غوغل"""

    list_display = ('id', 'task', 'conflict_type', 'resolution_status', 'row_index', 'created_at')
    list_filter = ('conflict_type', 'resolution_status', 'created_at')
    search_fields = ('task__mapping__name', 'description')
    readonly_fields = ('system_data', 'sheet_data', 'created_at', 'resolved_at')

@admin.register(GoogleSyncSchedule)
class GoogleSyncScheduleAdmin(admin.ModelAdmin):
    """إدارة جداول مزامنة غوغل"""

    list_display = ('mapping', 'is_active', 'frequency', 'last_run', 'next_run', 'total_runs')
    list_filter = ('is_active', 'frequency')
    search_fields = ('mapping__name',)
    readonly_fields = ('created_at', 'last_run', 'next_run', 'total_runs', 'successful_runs', 'failed_runs')
