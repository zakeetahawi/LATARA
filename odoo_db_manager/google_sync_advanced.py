"""
نماذج المزامنة المتقدمة مع Google Sheets
Advanced Google Sheets Sync Models
"""

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError
<<<<<<< HEAD
from datetime import timedelta
import json
=======
>>>>>>> source/main
import logging
import os
import sys
from datetime import time

logger = logging.getLogger('odoo_db_manager.google_sync_advanced')


class GoogleSheetMapping(models.Model):
    """
    نموذج تعيين أعمدة Google Sheets إلى حقول النظام
    Maps Google Sheets columns to system fields
    """

    FIELD_TYPES = [
        ('customer_code', 'رقم العميل (كود النظام)'),
        ('customer_name', 'اسم العميل'),
        ('customer_phone', 'رقم هاتف العميل'),
        ('customer_phone2', 'رقم الهاتف الثاني'),
        ('customer_email', 'بريد العميل الإلكتروني'),
        ('customer_address', 'عنوان العميل'),
        ('order_number', 'رقم الطلب'),
        ('invoice_number', 'رقم الفاتورة'),
        ('contract_number', 'رقم العقد'),
        ('order_date', 'تاريخ الطلب'),
        ('order_type', 'نوع الطلب'),
        ('order_status', 'حالة الطلب'),
        ('tracking_status', 'حالة التتبع'),
        ('total_amount', 'المبلغ الإجمالي'),
        ('paid_amount', 'المبلغ المدفوع'),
        ('delivery_type', 'نوع التسليم'),
        ('delivery_address', 'عنوان التسليم'),
        ('installation_status', 'حالة التركيب'),
        ('inspection_date', 'تاريخ المعاينة'),
        ('inspection_result', 'نتيجة المعاينة'),
        ('notes', 'ملاحظات'),
        ('branch', 'الفرع'),
        ('salesperson', 'البائع'),
        ('windows_count', 'عدد الشبابيك'),
        ('ignore', 'تجاهل هذا العمود'),
    ]

    # معلومات أساسية
    name = models.CharField(max_length=200, verbose_name='اسم التعيين')
    spreadsheet_id = models.CharField(max_length=500, verbose_name='معرف جدول Google')
    sheet_name = models.CharField(max_length=200, verbose_name='اسم الورقة', default='Sheet1')
    is_active = models.BooleanField(default=True, verbose_name='نشط')

    # إعدادات الصفوف
    header_row = models.PositiveIntegerField(default=1, verbose_name='صف العناوين')
    start_row = models.PositiveIntegerField(default=2, verbose_name='صف البداية')
    last_row_processed = models.PositiveIntegerField(null=True, blank=True, verbose_name='آخر صف تم معالجته')

    # تعيينات الأعمدة (JSON field)
    column_mappings = models.JSONField(default=dict, verbose_name='تعيينات الأعمدة')

    # إعدادات الإنشاء التلقائي
    auto_create_customers = models.BooleanField(default=True, verbose_name='إنشاء عملاء تلقائياً')
    auto_create_orders = models.BooleanField(default=True, verbose_name='إنشاء طلبات تلقائياً')
    auto_create_inspections = models.BooleanField(default=False, verbose_name='إنشاء معاينات تلقائياً')
    auto_create_installations = models.BooleanField(default=False, verbose_name='إنشاء تركيبات تلقائياً')

    # إعدادات الربط والتحديث
    update_existing = models.BooleanField(default=True, verbose_name='تحديث الموجود')
    conflict_resolution = models.CharField(
        max_length=20,
        choices=[
            ('skip', 'تجاهل التعارضات'),
            ('overwrite', 'الكتابة فوق البيانات الموجودة'),
            ('manual', 'الحل اليدوي للتعارضات'),
        ],
        default='manual',
        verbose_name='حل التعارضات'
    )

    # المزامنة العكسية (من النظام إلى Google Sheets)
    enable_reverse_sync = models.BooleanField(default=False, verbose_name='تمكين المزامنة العكسية')
    reverse_sync_fields = models.JSONField(default=list, verbose_name='حقول المزامنة العكسية')

    # معلومات التتبع
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    last_sync = models.DateTimeField(null=True, blank=True, verbose_name='آخر مزامنة')

    # إعدادات الفلترة والتحقق
    row_filter_conditions = models.JSONField(default=dict, blank=True, verbose_name='شروط فلترة الصفوف')
    data_validation_rules = models.JSONField(default=dict, blank=True, verbose_name='قواعد التحقق من البيانات')

    # القيم الافتراضية
    default_customer_category = models.ForeignKey(
        'customers.CustomerCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='تصنيف العميل الافتراضي'
    )
    default_customer_type = models.CharField(
        max_length=20,
        choices=[
            ('retail', 'أفراد'),
            ('wholesale', 'جملة'),
            ('corporate', 'شركات'),
        ],
        null=True,
        blank=True,
        verbose_name='نوع العميل الافتراضي'
    )
    default_branch = models.ForeignKey(
        'accounts.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='الفرع الافتراضي'
    )
    use_current_date_as_created = models.BooleanField(
        default=False,
        verbose_name='استخدام التاريخ الحالي كتاريخ الإضافة'
    )

    class Meta:
        verbose_name = 'تعيين Google Sheets'
        verbose_name_plural = 'تعيينات Google Sheets'
        db_table = 'google_sheet_mapping'

    def __str__(self):
        return f"{self.name} ({self.sheet_name})"

    def get_column_mappings(self):
        """إرجاع تعيينات الأعمدة مع التحقق من الصحة"""
        if isinstance(self.column_mappings, str):
            try:
                import json
                return json.loads(self.column_mappings)
            except (json.JSONDecodeError, TypeError):
                return {}
        return self.column_mappings or {}

    def get_reverse_sync_fields(self):
        """إرجاع حقول المزامنة العكسية"""
        return self.reverse_sync_fields or []
    
    def set_column_mappings(self, mappings_dict):
        """تحديث تعيينات الأعمدة"""
        if isinstance(mappings_dict, dict):
            self.column_mappings = mappings_dict
        else:
            self.column_mappings = {}

    def clean(self):
        """التحقق من صحة البيانات"""
        if not self.spreadsheet_id:
            raise ValidationError('معرف جدول Google مطلوب')
        
        if not self.sheet_name:
            raise ValidationError('اسم الورقة مطلوب')

        if self.start_row <= self.header_row:
            raise ValidationError('صف البداية يجب أن يكون بعد صف العناوين')

    def has_valid_mappings(self):
        """التحقق من وجود تعيينات صحيحة"""
        mappings = self.get_column_mappings()
        return bool(mappings and any(
            field_type != 'ignore' 
            for field_type in mappings.values()
        ))

    def get_mapped_columns(self):
        """إرجاع الأعمدة المُعينة فقط (بدون التجاهل)"""
        mappings = self.get_column_mappings()
        return {
            col: field_type 
            for col, field_type in mappings.items() 
            if field_type != 'ignore'
        }

    def get_customer_related_fields(self):
        """إرجاع الحقول المتعلقة بالعملاء"""
        mappings = self.get_mapped_columns()
        customer_fields = [
            'customer_code', 'customer_name', 'customer_phone', 
            'customer_phone2', 'customer_email', 'customer_address'
        ]
        return {
            col: field_type 
            for col, field_type in mappings.items() 
            if field_type in customer_fields
        }

    def get_order_related_fields(self):
        """إرجاع الحقول المتعلقة بالطلبات"""
        mappings = self.get_mapped_columns()
        order_fields = [
            'order_number', 'invoice_number', 'contract_number', 'order_date',
            'order_type', 'order_status', 'tracking_status', 'total_amount',
            'paid_amount', 'delivery_type', 'delivery_address', 'installation_status',
            'notes', 'branch', 'salesperson', 'windows_count'
        ]
        return {
            col: field_type 
            for col, field_type in mappings.items() 
            if field_type in order_fields
        }

    def should_create_customers(self):
        """تحديد ما إذا كان يجب إنشاء عملاء"""
        return self.auto_create_customers and bool(self.get_customer_related_fields())

    def should_create_orders(self):
        """تحديد ما إذا كان يجب إنشاء طلبات"""
        return self.auto_create_orders and bool(self.get_order_related_fields())

    def get_clean_column_mappings(self):
        """إرجاع تعيينات الأعمدة منظفة (بدون القيم الفارغة أو ignore)"""
        mappings = self.get_column_mappings()
        return {
            col: field_type 
            for col, field_type in mappings.items() 
            if field_type and field_type != 'ignore'
        }

    def validate_mappings(self):
        """التحقق من صحة تعيينات الأعمدة"""
        errors = []
        mappings = self.get_column_mappings()
        
        if not mappings:
            errors.append('لا توجد تعيينات أعمدة محددة')
            return errors
        
        # التحقق من وجود حقول العميل الأساسية إذا كان الإنشاء التلقائي مفعل
        if self.auto_create_customers:
            customer_fields = self.get_customer_related_fields()
            if not customer_fields:
                errors.append('يجب تعيين على الأقل حقل واحد للعميل عند تفعيل الإنشاء التلقائي للعملاء')
        
        # التحقق من وجود حقول الطلب الأساسية إذا كان الإنشاء التلقائي مفعل
        if self.auto_create_orders:
<<<<<<< HEAD
            required_fields.append('customer_name')  # العميل مطلوب للطلب

        # التحقق من وجود الحقول المطلوبة
        for field in required_fields:
            found = any(mapped_field == field for mapped_field in self.column_mappings.values())
            if not found:
                errors.append(f"الحقل المطلوب '{field}' غير موجود في التعيينات")

=======
            order_fields = self.get_order_related_fields()
            if not order_fields:
                errors.append('يجب تعيين على الأقل حقل واحد للطلب عند تفعيل الإنشاء التلقائي للطلبات')
        
        # التحقق من وجود تعيينات صالحة (ليست كلها ignore)
        valid_mappings = [v for v in mappings.values() if v != 'ignore']
        if not valid_mappings:
            errors.append('يجب أن يكون هناك على الأقل تعيين واحد صالح (غير مُتجاهل)')
        
>>>>>>> source/main
        return errors


class GoogleSyncTask(models.Model):
    """
    نموذج مهام المزامنة
    Sync Task Model
    """

    TASK_TYPES = [
        ('import', 'استيراد من Google Sheets'),
        ('export', 'تصدير إلى Google Sheets'),
        ('sync_bidirectional', 'مزامنة ثنائية الاتجاه'),
    ]

    TASK_STATUS = [
        ('pending', 'في الانتظار'),
        ('running', 'قيد التنفيذ'),
        ('completed', 'مكتملة'),
        ('failed', 'فشلت'),
        ('cancelled', 'ملغية'),
    ]

    # معلومات المهمة
    mapping = models.ForeignKey(
        GoogleSheetMapping, 
        on_delete=models.CASCADE, 
        verbose_name='التعيين',
        related_name='sync_tasks'
    )
    task_type = models.CharField(max_length=20, choices=TASK_TYPES, verbose_name='نوع المهمة')
    status = models.CharField(max_length=20, choices=TASK_STATUS, default='pending', verbose_name='الحالة')

    # معلومات التتبع
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='أنشأ بواسطة',
        related_name='created_sync_tasks',
        null=True,
        blank=True
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ البداية')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ الانتهاء')

    # النتائج
    result = models.JSONField(null=True, blank=True, verbose_name='النتيجة')
    rows_processed = models.PositiveIntegerField(default=0, verbose_name='الصفوف المعالجة')
    rows_successful = models.PositiveIntegerField(default=0, verbose_name='الصفوف الناجحة')
    rows_failed = models.PositiveIntegerField(default=0, verbose_name='الصفوف الفاشلة')

    # معلومات إضافية
    task_parameters = models.JSONField(default=dict, blank=True, verbose_name='معاملات المهمة')
    error_log = models.TextField(blank=True, verbose_name='سجل الأخطاء')

    class Meta:
        verbose_name = 'مهمة مزامنة'
        verbose_name_plural = 'مهام المزامنة'
        db_table = 'google_sync_task'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_task_type_display()} - {self.mapping.name} ({self.status})"

    def get_duration(self):
        """حساب مدة تنفيذ المهمة"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return timezone.now() - self.started_at
        return None

    def get_success_rate(self):
        """حساب معدل النجاح"""
        if self.rows_processed > 0:
            return (self.rows_successful / self.rows_processed) * 100
        return 0

    def is_running(self):
        """التحقق من كون المهمة قيد التنفيذ"""
        return self.status == 'running'

    def is_completed(self):
        """التحقق من اكتمال المهمة"""
        return self.status in ['completed', 'failed', 'cancelled']

    def start_execution(self):
        """بدء تنفيذ المهمة"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])

    def complete_execution(self, success=True, result=None, error_message=None):
        """إنهاء تنفيذ المهمة"""
        self.status = 'completed' if success else 'failed'
        self.completed_at = timezone.now()
        
        if result:
            self.result = result
            
        if error_message:
            self.error_log = error_message
            
        self.save(update_fields=['status', 'completed_at', 'result', 'error_log'])

    def update_progress(self, processed=0, successful=0, failed=0):
        """تحديث تقدم المهمة"""
        self.rows_processed = processed
        self.rows_successful = successful
        self.rows_failed = failed
        self.save(update_fields=['rows_processed', 'rows_successful', 'rows_failed'])
    
    def start_task(self):
        """بدء تنفيذ المهمة (alias لـ start_execution)"""
        self.start_execution()
    
    def mark_completed(self, result=None, success=True):
        """تحديد المهمة كمكتملة (alias لـ complete_execution)"""
        self.complete_execution(success=success, result=result)
    
    def mark_failed(self, error_message=None):
        """تحديد المهمة كفاشلة"""
        self.complete_execution(success=False, error_message=error_message)


class GoogleSyncConflict(models.Model):
    """
    نموذج تعارضات المزامنة
    Sync Conflict Model
    """

    CONFLICT_TYPES = [
        ('duplicate_customer', 'عميل مكرر'),
        ('duplicate_order', 'طلب مكرر'),
        ('data_mismatch', 'عدم تطابق البيانات'),
        ('missing_reference', 'مرجع مفقود'),
        ('validation_error', 'خطأ في التحقق'),
    ]

    RESOLUTION_STATUS = [
        ('pending', 'في الانتظار'),
        ('resolved', 'تم الحل'),
        ('ignored', 'متجاهل'),
    ]

    # معلومات التعارض
    task = models.ForeignKey(
        GoogleSyncTask, 
        on_delete=models.CASCADE, 
        verbose_name='المهمة',
        related_name='conflicts'
    )
    conflict_type = models.CharField(max_length=30, choices=CONFLICT_TYPES, verbose_name='نوع التعارض')
    row_number = models.PositiveIntegerField(default=1, verbose_name='رقم الصف')

    # البيانات المتعارضة
    sheet_data = models.JSONField(verbose_name='بيانات الجدول')
    existing_data = models.JSONField(null=True, blank=True, verbose_name='البيانات الموجودة')
    suggested_action = models.CharField(max_length=100, blank=True, verbose_name='الإجراء المقترح')

    # معلومات الحل
    resolution_status = models.CharField(
        max_length=20, 
        choices=RESOLUTION_STATUS, 
        default='pending', 
        verbose_name='حالة الحل'
    )
    resolution_action = models.CharField(max_length=100, blank=True, verbose_name='إجراء الحل')
    resolution_notes = models.TextField(blank=True, verbose_name='ملاحظات الحل')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ الحل')

    # معلومات التتبع
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')

    class Meta:
        verbose_name = 'تعارض مزامنة'
        verbose_name_plural = 'تعارضات المزامنة'
        db_table = 'google_sync_conflict'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_conflict_type_display()} - الصف {self.row_number}"

    def get_conflict_description(self):
        """وصف مفصل للتعارض"""
        descriptions = {
            'duplicate_customer': f'عميل مكرر في الصف {self.row_number}',
            'duplicate_order': f'طلب مكرر في الصف {self.row_number}',
            'data_mismatch': f'عدم تطابق البيانات في الصف {self.row_number}',
            'missing_reference': f'مرجع مفقود في الصف {self.row_number}',
            'validation_error': f'خطأ في التحقق في الصف {self.row_number}',
        }
        return descriptions.get(self.conflict_type, f'تعارض في الصف {self.row_number}')

    def is_pending(self):
        """التحقق من كون التعارض في انتظار الحل"""
        return self.resolution_status == 'pending'

    def resolve(self, action, notes=None):
        """حل التعارض"""
        self.resolution_status = 'resolved'
        self.resolution_action = action
        self.resolution_notes = notes or ''
        self.resolved_at = timezone.now()
        self.save(update_fields=[
            'resolution_status', 'resolution_action', 
            'resolution_notes', 'resolved_at'
        ])

    def ignore(self, notes=None):
        """تجاهل التعارض"""
        self.resolution_status = 'ignored'
        self.resolution_notes = notes or 'تم التجاهل'
        self.resolved_at = timezone.now()
        self.save(update_fields=['resolution_status', 'resolution_notes', 'resolved_at'])


class GoogleSyncSchedule(models.Model):
    """
    نموذج جدولة المزامنة
    Sync Schedule Model
    """

    FREQUENCY_CHOICES = [
        ('once', 'مرة واحدة'),
        ('daily', 'يومياً'),
        ('weekly', 'أسبوعياً'),
        ('monthly', 'شهرياً'),
        ('hourly', 'كل ساعة'),
    ]

    # معلومات الجدولة
    mapping = models.ForeignKey(
        GoogleSheetMapping, 
        on_delete=models.CASCADE, 
        verbose_name='التعيين',
        related_name='schedules'
    )
    name = models.CharField(max_length=200, default='جدولة افتراضية', verbose_name='اسم الجدولة')
    is_active = models.BooleanField(default=True, verbose_name='نشط')

    # إعدادات التوقيت
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='daily', verbose_name='التكرار')
    scheduled_time = models.TimeField(default=time(0, 0), verbose_name='وقت التنفيذ')
    next_run = models.DateTimeField(null=True, blank=True, verbose_name='التنفيذ القادم')

    # إعدادات المهمة
    task_type = models.CharField(
        max_length=20, 
        choices=GoogleSyncTask.TASK_TYPES, 
        default='import',
        verbose_name='نوع المهمة'
    )
    task_parameters = models.JSONField(default=dict, blank=True, verbose_name='معاملات المهمة')

    # معلومات التتبع
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    last_run = models.DateTimeField(null=True, blank=True, verbose_name='آخر تنفيذ')
    total_runs = models.PositiveIntegerField(default=0, verbose_name='إجمالي التنفيذ')
    successful_runs = models.PositiveIntegerField(default=0, verbose_name='التنفيذ الناجح')
    failed_runs = models.PositiveIntegerField(default=0, verbose_name='التنفيذ الفاشل')

    class Meta:
        verbose_name = 'جدولة مزامنة'
        verbose_name_plural = 'جدولة المزامنة'
        db_table = 'google_sync_schedule'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"

    def is_due(self):
        """التحقق من حان وقت التنفيذ"""
        if not self.is_active or not self.next_run:
            return False
        return timezone.now() >= self.next_run

    def calculate_next_run(self):
        """حساب موعد التنفيذ القادم"""
        from datetime import datetime, timedelta
        
        now = timezone.now()
        
        if self.frequency == 'once':
            self.next_run = None
        elif self.frequency == 'hourly':
            self.next_run = now + timedelta(hours=1)
        elif self.frequency == 'daily':
            self.next_run = now + timedelta(days=1)
        elif self.frequency == 'weekly':
            self.next_run = now + timedelta(weeks=1)
        elif self.frequency == 'monthly':
            self.next_run = now + timedelta(days=30)

    def record_execution(self, success=True):
        """تسجيل تنفيذ الجدولة"""
        self.last_run = timezone.now()
        self.total_runs += 1
        
        if success:
            self.successful_runs += 1
        else:
            self.failed_runs += 1
            
        self.calculate_next_run()
        self.save(update_fields=['last_run', 'total_runs', 'successful_runs', 'failed_runs', 'next_run'])
