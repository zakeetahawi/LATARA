"""
إدارة Django Admin للمزامنة المتقدمة مع Google Sheets
Django Admin for Advanced Google Sheets Sync
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.safestring import mark_safe
from django import forms

from .google_sync_advanced import (
    GoogleSheetMapping, GoogleSyncTask, GoogleSyncConflict, GoogleSyncSchedule
)


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
        """عرض تعيينات الأعمدة بشكل مختصر (اسم العمود ونوعه فقط)"""
        if not obj.column_mappings:
            return _('لا توجد تعيينات')
        
        html = '<table style="width:100%">'
        html += '<tr><th>اسم العمود</th><th>النوع</th></tr>'
        
        # محاولة جلب أسماء الأعمدة من الجدول إذا أمكن
        headers = []
        try:
            from .google_sheets_import import GoogleSheetsImporter
            importer = GoogleSheetsImporter()
            importer.initialize()
            headers = importer.get_sheet_data(obj.sheet_name)[obj.header_row - 1]
        except Exception:
            pass

        for col_key, field_type in obj.column_mappings.items():
            # col_key هو رقم العمود كنص غالباً
            try:
                col_index = int(col_key)
                col_name = headers[col_index] if headers and col_index < len(headers) else col_key
            except Exception:
                col_name = col_key
            # البحث عن اسم النوع
            field_name = field_type
            for choice in obj.FIELD_TYPES:
                if choice[0] == field_type:
                    field_name = choice[1]
                    break
            html += f'<tr><td>{col_name}</td><td>{field_name}</td></tr>'
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
        """
        حفظ النموذج مع تحديد المستخدم
        التأكد من أن جميع المفاتيح في column_mappings هي أرقام أعمدة (وليس أسماء)
        """
        if obj.column_mappings:
            # محاولة جلب أسماء الأعمدة من الجدول
            headers = []
            try:
                from .google_sheets_import import GoogleSheetsImporter
                importer = GoogleSheetsImporter()
                importer.initialize()
                headers = importer.get_sheet_data(obj.sheet_name)[obj.header_row - 1]
            except Exception:
                pass
            new_mappings = {}
            for key, value in obj.column_mappings.items():
                # إذا كان المفتاح اسم عمود وليس رقم
                if headers and key in headers:
                    col_index = headers.index(key)
                    new_mappings[str(col_index)] = value
                else:
                    new_mappings[str(key)] = value
            obj.column_mappings = new_mappings
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    save_model.__doc__ += "\n\nملاحظة: يتم تلقائياً تحويل أي اسم عمود إلى رقم العمود الصحيح عند الحفظ لضمان سلامة المزامنة."
    
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
        if not change:  # إنشاء جديد
            obj.created_by = request.user
        
        # حساب موعد التشغيل القادم
        if obj.is_active:
            obj.calculate_next_run()
        
        super().save_model(request, obj, form, change)


# تخصيص عنوان الإدارة
admin.site.site_header = _('إدارة نظام المزامنة المتقدمة')
admin.site.site_title = _('المزامنة المتقدمة')
admin.site.index_title = _('لوحة تحكم المزامنة المتقدمة')


# إضافة أعمال مخصصة
from django.contrib.admin import AdminSite
from django.urls import path
from django.http import HttpResponseRedirect
from django.contrib import messages

class AdvancedSyncAdminSite(AdminSite):
    """موقع إدارة مخصص للمزامنة المتقدمة"""
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('sync-all/', self.admin_view(self.sync_all_view), name='sync_all'),
            path('validate-mappings/', self.admin_view(self.validate_mappings_view), name='validate_mappings'),
        ]
        return custom_urls + urls
    
    def sync_all_view(self, request):
        """تشغيل مزامنة جميع التعيينات النشطة"""
        from .tasks import sync_all_active_mappings
        
        try:
            result = sync_all_active_mappings.delay()
            messages.success(request, f"تم بدء مزامنة جميع التعيينات النشطة. معرف المهمة: {result.id}")
        except Exception as e:
            messages.error(request, f"خطأ في بدء المزامنة: {str(e)}")
        
        return HttpResponseRedirect('../')
    
    def validate_mappings_view(self, request):
        """التحقق من صحة جميع التعيينات"""
        from .tasks import validate_all_mappings
        
        try:
            result = validate_all_mappings.delay()
            messages.success(request, f"تم بدء التحقق من التعيينات. معرف المهمة: {result.id}")
        except Exception as e:
            messages.error(request, f"خطأ في بدء التحقق: {str(e)}")
        
        return HttpResponseRedirect('../')


# إنشاء موقع إدارة مخصص
advanced_sync_admin = AdvancedSyncAdminSite(name='advanced_sync_admin')

# تسجيل النماذج في الموقع المخصص
advanced_sync_admin.register(GoogleSheetMapping, GoogleSheetMappingAdmin)
advanced_sync_admin.register(GoogleSyncTask, GoogleSyncTaskAdmin)
advanced_sync_admin.register(GoogleSyncConflict, GoogleSyncConflictAdmin)
advanced_sync_admin.register(GoogleSyncSchedule, GoogleSyncScheduleAdmin)
