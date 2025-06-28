"""
نماذج المزامنة المتقدمة مع Google Sheets
Advanced Google Sheets Sync Models
"""

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
import json
import logging
import os
import sys

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
        ('customer_type', 'نوع العميل'),
        ('customer_category', 'فئة العميل'),
        ('branch', 'الفرع'),
        ('salesperson', 'البائع'),
        ('order_number', 'رقم الطلب'),
        ('order_status', 'حالة الطلب'),
        ('order_date', 'تاريخ الطلب'),
        ('invoice_number', 'رقم الفاتورة'),
        ('total_amount', 'المبلغ الإجمالي'),
        ('paid_amount', 'المبلغ المدفوع'),
        ('remaining_amount', 'المبلغ المتبقي'),
        ('inspection_date', 'تاريخ المعاينة'),
        ('installation_date', 'تاريخ التركيب'),
        ('notes', 'ملاحظات'),
    ]

    name = models.CharField(_('اسم التعيين'), max_length=100)

    # معلومات Google Sheets
    spreadsheet_id = models.CharField(_('معرف جدول البيانات'), max_length=255)
    sheet_name = models.CharField(_('اسم الصفحة'), max_length=100)
    header_row = models.PositiveIntegerField(_('صف العناوين'), default=1)
    start_row = models.PositiveIntegerField(_('صف البداية'), default=2)
    last_row_processed = models.PositiveIntegerField(_('آخر صف تمت معالجته'), default=0)

    # تعيينات الأعمدة
    column_mappings = models.JSONField(
        _('تعيينات الأعمدة'),
        default=dict,
        help_text=_('تعيين أعمدة Google Sheets إلى حقول النظام')
    )

    # إعدادات المزامنة
    auto_create_customers = models.BooleanField(_('إنشاء عملاء تلقائياً'), default=True)
    auto_create_orders = models.BooleanField(_('إنشاء طلبات تلقائياً'), default=True)
    auto_create_inspections = models.BooleanField(_('إنشاء معاينات تلقائياً'), default=False)
    auto_create_installations = models.BooleanField(_('إنشاء تركيبات تلقائياً'), default=False)
    update_existing_customers = models.BooleanField(_('تحديث العملاء الموجودين'), default=True)
    update_existing_orders = models.BooleanField(_('تحديث الطلبات الموجودة'), default=True)
    enable_reverse_sync = models.BooleanField(_('تمكين المزامنة العكسية'), default=False)

    # القيم الافتراضية
    default_customer_category = models.ForeignKey(
        'customers.CustomerCategory',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name=_('فئة العميل الافتراضية'),
        related_name='sheet_mappings'
    )
    default_customer_type = models.CharField(
        _('نوع العميل الافتراضي'),
        max_length=50,
        blank=True,
        null=True
    )
    default_branch = models.ForeignKey(
        'accounts.Branch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name=_('الفرع الافتراضي'),
        related_name='sheet_mappings'
    )
    use_current_date_as_created = models.BooleanField(
        _('استخدام التاريخ الحالي كتاريخ إنشاء'),
        default=True
    )

    # معلومات النظام
    is_active = models.BooleanField(_('نشط'), default=True)
    last_sync = models.DateTimeField(_('آخر مزامنة'), null=True, blank=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('تم الإنشاء بواسطة'),
        related_name='created_sheet_mappings'
    )

    class Meta:
        verbose_name = _('تعيين Google Sheets')
        verbose_name_plural = _('تعيينات Google Sheets')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.sheet_name})"

    def get_column_mapping(self, column_identifier):
        """
        الحصول على تعيين العمود باستخدام المعرف (الاسم أو الرقم)
        """
        if not self.column_mappings:
            return None

        # البحث بالاسم
        if isinstance(column_identifier, str):
            return self.column_mappings.get(column_identifier)

        # البحث بالرقم
        return self.column_mappings.get(str(column_identifier))

    def validate_mappings(self):
        """
        التحقق من صحة التعيينات
        """
        errors = []

        # التحقق من وجود تعيينات
        if not self.column_mappings:
            errors.append("لا توجد تعيينات للأعمدة")
            return errors

        # التحقق من وجود الحقول الأساسية
        required_fields = []
        if self.auto_create_customers:
            required_fields.append('customer_name')

        if self.auto_create_orders:
            required_fields.append('customer_name')  # العميل مطلوب للطلب

        # التحقق من وجود الحقول المطلوبة
        for field in required_fields:
            found = any(mapped_field == field for mapped_field in self.column_mappings.values())
            if not found:
                errors.append(f"الحقل المطلوب '{field}' غير موجود في التعيينات")

        return errors


class GoogleSyncTask(models.Model):
    """
    نموذج مهام المزامنة
    Sync Tasks Model
    """

    TASK_TYPES = [
        ('import', _('استيراد من Google Sheets')),
        ('export', _('تصدير إلى Google Sheets')),
        ('sync', _('مزامنة ثنائية الاتجاه')),
        ('reverse_sync', _('مزامنة عكسية')),
    ]

    STATUS_CHOICES = [
        ('pending', _('في الانتظار')),
        ('running', _('قيد التنفيذ')),
        ('completed', _('مكتمل')),
        ('failed', _('فشل')),
        ('cancelled', _('ملغي')),
    ]

    mapping = models.ForeignKey(
        GoogleSheetMapping,
        on_delete=models.CASCADE,
        related_name='sync_tasks',
        verbose_name=_('تعيين الصفحة')
    )

    task_type = models.CharField(_('نوع المهمة'), max_length=20, choices=TASK_TYPES)
    status = models.CharField(_('الحالة'), max_length=20, choices=STATUS_CHOICES, default='pending')

    # معلومات التنفيذ
    started_at = models.DateTimeField(_('بدء التنفيذ'), null=True, blank=True)
    completed_at = models.DateTimeField(_('انتهاء التنفيذ'), null=True, blank=True)

    # إحصائيات
    total_rows = models.IntegerField(_('إجمالي الصفوف'), default=0)
    processed_rows = models.IntegerField(_('الصفوف المعالجة'), default=0)
    successful_rows = models.IntegerField(_('الصفوف الناجحة'), default=0)
    failed_rows = models.IntegerField(_('الصفوف الفاشلة'), default=0)

    # تفاصيل النتائج
    results = models.JSONField(
        _('نتائج التنفيذ'),
        default=dict,
        help_text=_('تفاصيل نتائج المزامنة')
    )

    error_message = models.TextField(_('رسالة الخطأ'), blank=True)
    error_details = models.JSONField(_('تفاصيل الأخطاء'), default=list)

    # معلومات النظام
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('تم الإنشاء بواسطة')
    )

    # إعدادات المهمة
    is_scheduled = models.BooleanField(_('مجدولة'), default=False)
    schedule_frequency = models.IntegerField(_('تكرار الجدولة (بالدقائق)'), default=60)
    next_run = models.DateTimeField(_('التشغيل القادم'), null=True, blank=True)

    class Meta:
        verbose_name = _('مهمة مزامنة')
        verbose_name_plural = _('مهام المزامنة')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_task_type_display()} - {self.mapping.name}"

    def start_task(self):
        """بدء تنفيذ المهمة"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])

    def complete_task(self, results=None):
        """إكمال المهمة"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if results:
            self.results = results
        self.save(update_fields=['status', 'completed_at', 'results'])

    def fail_task(self, error_message, error_details=None):
        """فشل المهمة"""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        if error_details:
            self.error_details = error_details
        self.save(update_fields=['status', 'completed_at', 'error_message', 'error_details'])

    def mark_completed(self, result_data=None):
        """إنهاء المهمة بنجاح"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if result_data:
            self.results = result_data
            # تحديث الإحصائيات من النتائج
            if 'stats' in result_data:
                stats = result_data['stats']
                self.total_rows = stats.get('total_rows', 0)
                self.processed_rows = stats.get('processed_rows', 0)
                self.successful_rows = stats.get('customers_created', 0) + stats.get('orders_created', 0) + stats.get('customers_updated', 0) + stats.get('orders_updated', 0)
                self.failed_rows = len(stats.get('errors', []))
        self.save(update_fields=['status', 'completed_at', 'results', 'total_rows', 'processed_rows', 'successful_rows', 'failed_rows'])

    def mark_failed(self, error_message, error_details=None):
        """فشل المهمة (اسم بديل)"""
        return self.fail_task(error_message, error_details)

    def get_progress_percentage(self):
        """حساب نسبة التقدم"""
        if self.total_rows == 0:
            return 0
        return int((self.processed_rows / self.total_rows) * 100)

    def get_duration(self):
        """حساب مدة التنفيذ"""
        if not self.started_at:
            return None
        end_time = self.completed_at or timezone.now()
        return end_time - self.started_at


class GoogleSyncConflict(models.Model):
    """
    نموذج تعارضات المزامنة
    Sync Conflicts Model
    """

    CONFLICT_TYPES = [
        ('duplicate', _('تكرار')),
        ('validation_error', _('خطأ في التحقق')),
        ('missing_data', _('بيانات مفقودة')),
        ('data_mismatch', _('عدم تطابق البيانات')),
        ('other', _('أخرى')),
    ]

    RESOLUTION_STATUS = [
        ('pending', _('في انتظار الحل')),
        ('resolved', _('تم الحل')),
        ('ignored', _('تم التجاهل')),
    ]

    task = models.ForeignKey(
        GoogleSyncTask,
        on_delete=models.CASCADE,
        related_name='conflicts',
        verbose_name=_('مهمة المزامنة')
    )

    conflict_type = models.CharField(_('نوع التعارض'), max_length=20, choices=CONFLICT_TYPES)
    field_name = models.CharField(_('اسم الحقل'), max_length=100)
    row_index = models.IntegerField(_('رقم الصف'), default=0)

    system_data = models.JSONField(_('بيانات النظام'), default=dict)
    sheet_data = models.JSONField(_('بيانات الجدول'), default=dict)

    description = models.TextField(_('وصف التعارض'))
    resolution_status = models.CharField(
        _('حالة الحل'),
        max_length=20,
        choices=RESOLUTION_STATUS,
        default='pending'
    )
    resolution_notes = models.TextField(_('ملاحظات الحل'), blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name=_('تم الحل بواسطة')
    )
    resolved_at = models.DateTimeField(_('تاريخ الحل'), null=True, blank=True)

    # معلومات النظام
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)

    class Meta:
        verbose_name = _('تعارض مزامنة')
        verbose_name_plural = _('تعارضات المزامنة')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_conflict_type_display()} - صف {self.row_index}"

    def resolve(self, user, notes=''):
        """حل التعارض"""
        self.resolution_status = 'resolved'
        self.resolution_notes = notes
        self.resolved_by = user
        self.resolved_at = timezone.now()
        self.save(update_fields=['resolution_status', 'resolution_notes', 'resolved_by', 'resolved_at'])

    def ignore(self, user, notes=''):
        """تجاهل التعارض"""
        self.resolution_status = 'ignored'
        self.resolution_notes = notes
        self.resolved_by = user
        self.resolved_at = timezone.now()
        self.save(update_fields=['resolution_status', 'resolution_notes', 'resolved_by', 'resolved_at'])


class GoogleSyncSchedule(models.Model):
    """
    نموذج جدولة المزامنة
    Sync Schedule Model
    """

    FREQUENCY_CHOICES = [
        ('hourly', _('كل ساعة')),
        ('daily', _('يومياً')),
        ('weekly', _('أسبوعياً')),
        ('monthly', _('شهرياً')),
        ('custom', _('مخصص')),
    ]

    mapping = models.ForeignKey(
        GoogleSheetMapping,
        on_delete=models.CASCADE,
        related_name='schedules',
        verbose_name=_('تعيين الصفحة')
    )

    name = models.CharField(_('اسم الجدولة'), max_length=100)
    description = models.TextField(_('وصف الجدولة'), blank=True)

    frequency = models.CharField(_('التكرار'), max_length=20, choices=FREQUENCY_CHOICES, default='daily')
    custom_minutes = models.PositiveIntegerField(_('دقائق مخصصة'), default=60)
    
    is_active = models.BooleanField(_('نشط'), default=True)
    last_run = models.DateTimeField(_('آخر تشغيل'), null=True, blank=True)
    next_run = models.DateTimeField(_('التشغيل القادم'), null=True, blank=True)

    total_runs = models.PositiveIntegerField(_('إجمالي مرات التشغيل'), default=0)
    successful_runs = models.PositiveIntegerField(_('مرات التشغيل الناجحة'), default=0)
    failed_runs = models.PositiveIntegerField(_('مرات التشغيل الفاشلة'), default=0)

    # معلومات النظام
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('تم الإنشاء بواسطة')
    )

    class Meta:
        verbose_name = _('جدولة مزامنة')
        verbose_name_plural = _('جدولات المزامنة')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.mapping.name}"

    def save(self, *args, **kwargs):
        # حساب التشغيل القادم عند الإنشاء
        if not self.next_run:
            self.calculate_next_run()
        super().save(*args, **kwargs)

    def calculate_next_run(self):
        """حساب موعد التشغيل القادم"""
        now = timezone.now()
        
        if self.frequency == 'hourly':
            self.next_run = now + timedelta(hours=1)
        elif self.frequency == 'daily':
            self.next_run = now + timedelta(days=1)
        elif self.frequency == 'weekly':
            self.next_run = now + timedelta(weeks=1)
        elif self.frequency == 'monthly':
            # تقريبي - 30 يوم
            self.next_run = now + timedelta(days=30)
        else:  # custom
            self.next_run = now + timedelta(minutes=self.custom_minutes)

    def record_run(self, success=True):
        """تسجيل تشغيل"""
        self.last_run = timezone.now()
        self.total_runs += 1
        
        if success:
            self.successful_runs += 1
        else:
            self.failed_runs += 1
            
        self.calculate_next_run()
        self.save(update_fields=['last_run', 'total_runs', 'successful_runs', 'failed_runs', 'next_run'])
