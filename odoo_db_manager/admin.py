"""
تسجيل النماذج في واجهة الإدارة
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.safestring import mark_safe
from django import forms
from django.utils import timezone

from .models import Database, Backup
from .google_sync import GoogleSyncConfig, GoogleSyncLog
from .google_sync_advanced import (
    GoogleSheetMapping, GoogleSyncTask, GoogleSyncConflict, GoogleSyncSchedule
)

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


# ==========================================
# Advanced Google Sheets Sync Admin
# ==========================================

@admin.register(GoogleSheetMapping)
class GoogleSheetMappingAdmin(admin.ModelAdmin):
    """إدارة تعيينات Google Sheets"""
    
    list_display = [
        'name', 'sheet_name', 'is_active', 'last_sync', 
        'auto_create_customers', 'auto_create_orders', 'enable_reverse_sync',
        'created_at'
    ]
    
    list_filter = [
        'is_active', 'auto_create_customers', 'auto_create_orders',
        'auto_create_inspections', 'auto_create_installations',
        'enable_reverse_sync', 'created_at'
    ]
    
    search_fields = ['name', 'spreadsheet_id', 'sheet_name']
    
    readonly_fields = [
        'created_at', 'updated_at', 'last_sync', 'last_row_processed',
        'column_mappings_display', 'reverse_sync_fields_display'
    ]
    
    fieldsets = (
        (_('معلومات أساسية'), {
            'fields': ('name', 'spreadsheet_id', 'sheet_name', 'is_active')
        }),
        (_('إعدادات الصفوف'), {
            'fields': ('header_row', 'start_row', 'last_row_processed')
        }),
        (_('إعدادات الإنشاء التلقائي'), {
            'fields': (
                'auto_create_customers', 'auto_create_orders',
                'auto_create_inspections', 'auto_create_installations'
            )
        }),
        (_('إعدادات التحديث'), {
            'fields': ('update_existing_customers', 'update_existing_orders')
        }),
        (_('المزامنة العكسية'), {
            'fields': ('enable_reverse_sync', 'reverse_sync_fields_display'),
            'classes': ('collapse',)
        }),
        (_('تعيين الأعمدة'), {
            'fields': ('column_mappings_display',),
            'classes': ('collapse',)
        }),
        (_('معلومات النظام'), {
            'fields': ('created_by', 'created_at', 'updated_at', 'last_sync'),
            'classes': ('collapse',)
        })
    )
    
    def column_mappings_display(self, obj):
        """عرض تعيينات الأعمدة بشكل مختصر"""
        if not obj.column_mappings:
            return _('لا توجد تعيينات')
        
        html = '<table style="width:100%">'
        html += '<tr><th>اسم العمود</th><th>النوع</th></tr>'
        
        for col_key, field_type in obj.column_mappings.items():
            html += f'<tr><td>{col_key}</td><td>{field_type}</td></tr>'
        html += '</table>'
        return mark_safe(html)
    
    column_mappings_display.short_description = _('تعيينات الأعمدة')
    
    def reverse_sync_fields_display(self, obj):
        """عرض حقول المزامنة العكسية"""
        if not obj.reverse_sync_fields:
            return _('لا توجد حقول')
        
        return ', '.join(obj.reverse_sync_fields)
    
    reverse_sync_fields_display.short_description = _('حقول المزامنة العكسية')
    
    def save_model(self, request, obj, form, change):
        """حفظ النموذج مع تحديد المستخدم"""
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class GoogleSyncConflictInline(admin.TabularInline):
    """عرض التعارضات كـ inline"""
    model = GoogleSyncConflict
    extra = 0
    readonly_fields = ['conflict_type', 'field_name', 'row_index', 'description', 'created_at']
    fields = ['conflict_type', 'field_name', 'row_index', 'resolution_status', 'created_at']
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(GoogleSyncTask)
class GoogleSyncTaskAdmin(admin.ModelAdmin):
    """إدارة مهام المزامنة"""
    
    list_display = [
        'id', 'mapping', 'task_type', 'status', 'progress_display',
        'started_at', 'completed_at', 'duration_display'
    ]
    
    list_filter = [
        'task_type', 'status', 'is_scheduled', 'created_at', 'started_at'
    ]
    
    search_fields = ['mapping__name', 'error_message']
    
    readonly_fields = [
        'created_at', 'started_at', 'completed_at', 'duration_display',
        'progress_display', 'results_display', 'error_details_display'
    ]
    
    fieldsets = (
        (_('معلومات المهمة'), {
            'fields': ('mapping', 'task_type', 'status', 'created_by')
        }),
        (_('التوقيت'), {
            'fields': ('created_at', 'started_at', 'completed_at', 'duration_display')
        }),
        (_('الإحصائيات'), {
            'fields': (
                'total_rows', 'processed_rows', 'successful_rows', 'failed_rows',
                'progress_display'
            )
        }),
        (_('الجدولة'), {
            'fields': ('is_scheduled', 'schedule_frequency', 'next_run'),
            'classes': ('collapse',)
        }),
        (_('النتائج'), {
            'fields': ('results_display',),
            'classes': ('collapse',)
        }),
        (_('الأخطاء'), {
            'fields': ('error_message', 'error_details_display'),
            'classes': ('collapse',)
        })
    )
    
    inlines = [GoogleSyncConflictInline]
    
    def progress_display(self, obj):
        """عرض نسبة التقدم"""
        if obj.total_rows == 0:
            return _('غير محدد')
        
        progress = obj.get_progress_percentage()
        color = 'green' if progress == 100 else 'orange' if progress > 50 else 'red'
        
        return format_html(
            '<div style="width:100px; background-color:#f0f0f0; border-radius:3px;">'
            '<div style="width:{}%; background-color:{}; height:20px; border-radius:3px; text-align:center; color:white;">'
            '{}%</div></div>',
            progress, color, progress
        )
    
    progress_display.short_description = _('التقدم')
    
    def duration_display(self, obj):
        """عرض مدة التنفيذ"""
        duration = obj.get_duration()
        if not duration:
            return _('غير محدد')
        
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    duration_display.short_description = _('المدة')
    
    def results_display(self, obj):
        """عرض النتائج بشكل منسق"""
        if not obj.results:
            return _('لا توجد نتائج')
        
        html = '<table style="width:100%">'
        for key, value in obj.results.items():
            html += f'<tr><td><strong>{key}:</strong></td><td>{value}</td></tr>'
        html += '</table>'
        
        return mark_safe(html)
    
    results_display.short_description = _('النتائج')
    
    def error_details_display(self, obj):
        """عرض تفاصيل الأخطاء"""
        if not obj.error_details:
            return _('لا توجد أخطاء')
        
        html = '<ul>'
        for error in obj.error_details:
            html += f'<li>{error}</li>'
        html += '</ul>'
        
        return mark_safe(html)
    
    error_details_display.short_description = _('تفاصيل الأخطاء')
    
    def has_add_permission(self, request):
        """منع إضافة مهام يدوياً"""
        return False


@admin.register(GoogleSyncConflict)
class GoogleSyncConflictAdmin(admin.ModelAdmin):
    """إدارة تعارضات المزامنة"""
    
    list_display = [
        'id', 'task', 'conflict_type', 'field_name', 'row_index',
        'resolution_status', 'created_at', 'resolved_at'
    ]
    
    list_filter = [
        'conflict_type', 'resolution_status',
        'created_at', 'resolved_at'
    ]
    
    search_fields = ['task__mapping__name', 'description', 'resolution_notes']
    
    readonly_fields = [
        'task', 'conflict_type', 'field_name', 'row_index',
        'system_data_display', 'sheet_data_display', 'description',
        'created_at', 'resolved_at'
    ]
    
    fieldsets = (
        (_('معلومات التعارض'), {
            'fields': ('task', 'conflict_type', 'field_name', 'row_index')
        }),
        (_('وصف التعارض'), {
            'fields': ('description',)
        }),
        (_('البيانات'), {
            'fields': ('system_data_display', 'sheet_data_display'),
            'classes': ('collapse',)
        }),
        (_('الحل'), {
            'fields': ('resolution_status', 'resolution_notes', 'resolved_by')
        }),
        (_('التوقيت'), {
            'fields': ('created_at', 'resolved_at'),
            'classes': ('collapse',)
        })
    )
    
    def system_data_display(self, obj):
        """عرض بيانات النظام"""
        if not obj.system_data:
            return _('لا توجد بيانات')
        
        html = '<table style="width:100%">'
        for key, value in obj.system_data.items():
            html += f'<tr><td><strong>{key}:</strong></td><td>{value}</td></tr>'
        html += '</table>'
        
        return mark_safe(html)
    
    system_data_display.short_description = _('بيانات النظام')
    
    def sheet_data_display(self, obj):
        """عرض بيانات Google Sheets"""
        if not obj.sheet_data:
            return _('لا توجد بيانات')
        
        html = '<table style="width:100%">'
        for key, value in obj.sheet_data.items():
            html += f'<tr><td><strong>{key}:</strong></td><td>{value}</td></tr>'
        html += '</table>'
        
        return mark_safe(html)
    
    sheet_data_display.short_description = _('بيانات Google Sheets')
    
    def save_model(self, request, obj, form, change):
        """حفظ النموذج مع تحديد المستخدم الذي حل التعارض"""
        if change and 'resolution_status' in form.changed_data:
            if obj.resolution_status != 'pending' and not obj.resolved_by:
                obj.resolved_by = request.user
                obj.resolved_at = timezone.now()
        
        super().save_model(request, obj, form, change)


@admin.register(GoogleSyncSchedule)
class GoogleSyncScheduleAdmin(admin.ModelAdmin):
    """إدارة جدولة المزامنة"""
    
    list_display = [
        'mapping', 'is_active', 'frequency_display', 'last_run',
        'next_run', 'success_rate_display', 'created_at'
    ]
    
    list_filter = ['is_active', 'frequency', 'created_at']
    
    search_fields = ['mapping__name']
    
    readonly_fields = [
        'last_run', 'next_run', 'total_runs', 'successful_runs', 'failed_runs',
        'success_rate_display', 'created_at'
    ]
    
    fieldsets = (
        (_('الجدولة'), {
            'fields': ('mapping', 'is_active', 'frequency', 'custom_minutes')
        }),
        (_('التوقيت'), {
            'fields': ('last_run', 'next_run')
        }),
        (_('الإحصائيات'), {
            'fields': (
                'total_runs', 'successful_runs', 'failed_runs', 'success_rate_display'
            )
        }),
        (_('معلومات النظام'), {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        })
    )
    
    def frequency_display(self, obj):
        """عرض التكرار بشكل مفهوم"""
        if obj.frequency == 'custom':
            return f"كل {obj.custom_minutes} دقيقة"
        
        frequency_map = {
            'hourly': _('كل ساعة'),
            'daily': _('يومياً'),
            'weekly': _('أسبوعياً'),
            'monthly': _('شهرياً'),
        }
        
        return frequency_map.get(obj.frequency, obj.frequency)
    
    frequency_display.short_description = _('التكرار')
    
    def success_rate_display(self, obj):
        """عرض معدل النجاح"""
        if obj.total_runs == 0:
            return _('لا توجد تشغيلات')
        
        success_rate = (obj.successful_runs / obj.total_runs) * 100
        color = 'green' if success_rate >= 80 else 'orange' if success_rate >= 60 else 'red'
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color, success_rate
        )
    
    success_rate_display.short_description = _('معدل النجاح')
    
    def save_model(self, request, obj, form, change):
        """حفظ النموذج مع تحديد المستخدم"""
        if not change:
            obj.created_by = request.user
        
        if obj.is_active:
            obj.calculate_next_run()
        
        super().save_model(request, obj, form, change)
