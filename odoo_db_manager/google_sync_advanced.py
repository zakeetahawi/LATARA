"""
نماذج المزامنة المتقدمة مع Google Sheets
Advanced Google Sheets Sync Models
"""

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.exceptions import ValidationError
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
            found = False
            for mapped_field in self.column_mappings.values():
                if mapped_field == field:
                    found = True
                    break
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


class AdvancedSyncService:
    """
    خدمة المزامنة المتقدمة مع Google Sheets
    Advanced Google Sheets Sync Service
    """

    def __init__(self, mapping):
        self.mapping = mapping

    def sync_from_sheets(self, task):
        """
        تنفيذ المزامنة من Google Sheets باستخدام التعيينات المخصصة
        """
        logger.info(f"SYNC LOG PATH = {os.path.join(settings.BASE_DIR, 'media', 'sync_from_sheets.log')}")
        print("=== SYNC_FROM_SHEETS CALLED ===", file=sys.stderr, flush=True)
        logger.info("=== SYNC_FROM_SHEETS CALLED === (triggered from UI or API)")
        logger.info("=== TEST LOG ENTRY === (should appear in sync_from_sheets.log)")

        try:
            from .google_sheets_import import GoogleSheetsImporter

            # إنشاء importer مع معرف الجدول الصحيح
            importer = GoogleSheetsImporter()
            importer.initialize()

            # حفظ المعرف الأصلي وتحديثه بمعرف التعيين
            original_id = getattr(importer.config, 'spreadsheet_id', None)

            try:
                # تحديث معرف الجدول إلى معرف التعيين
                if hasattr(importer.config, 'spreadsheet_id'):
                    importer.config.spreadsheet_id = self.mapping.spreadsheet_id

                # جلب بيانات الجدول
                sheet_data = importer.get_sheet_data(self.mapping.sheet_name)

                if not sheet_data:
                    return {
                        'success': False,
                        'error': 'لا توجد بيانات في الجدول'
                    }

                # معالجة البيانات باستخدام التعيينات المخصصة
                result = self.process_custom_data(sheet_data, task)

                return result

            finally:
                # استعادة المعرف الأصلي
                if original_id and hasattr(importer.config, 'spreadsheet_id'):
                    importer.config.spreadsheet_id = original_id

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def process_custom_data(self, sheet_data, task):
        """
        معالجة البيانات باستخدام تعيينات الأعمدة المخصصة
        """
        try:
            # التحقق من وجود تعيينات الأعمدة
            if not self.mapping.column_mappings:
                return {
                    'success': False,
                    'error': 'لا توجد تعيينات أعمدة محفوظة. يرجى تحديث تعيينات الأعمدة أولاً.'
                }

            # جلب عناوين الأعمدة من الصف المحدد
            if len(sheet_data) < self.mapping.header_row:
                return {
                    'success': False,
                    'error': f'الجدول لا يحتوي على صف العناوين المحدد (صف {self.mapping.header_row})'
                }

            headers = sheet_data[self.mapping.header_row - 1]

            # جلب بيانات الصفوف من الصف المحدد
            if len(sheet_data) < self.mapping.start_row:
                return {
                    'success': False,
                    'error': f'الجدول لا يحتوي على بيانات من الصف المحدد (صف {self.mapping.start_row})'
                }

            data_rows = sheet_data[self.mapping.start_row - 1:]

            # إحصائيات المعالجة
            stats = {
                'total_rows': len(data_rows),
                'processed_rows': 0,
                'customers_created': 0,
                'customers_updated': 0,
                'orders_created': 0,
                'orders_updated': 0,
                'inspections_created': 0,
                'installations_created': 0,
                'errors': [],
                'warnings': []
            }

            # معالجة كل صف
            for row_index, row_data in enumerate(data_rows, start=self.mapping.start_row):
                try:
                    # تحويل الصف إلى قاموس باستخدام التعيينات
                    row_dict = self.map_row_to_fields(headers, row_data, row_index)

                    # معالجة البيانات حتى لو كانت ناقصة
                    row_result = None
                    if row_dict:
                        # معالجة البيانات وإنشاء/تحديث السجلات
                        row_result = self.process_row_data(row_dict, row_index, task)
                    else:
                        # حتى لو لم يكن هناك تعيين، حاول معالجة الصف مباشرة
                        if any(str(cell).strip() for cell in row_data):
                            # إنشاء قاموس بسيط من البيانات المتاحة
                            simple_dict = {}
                            for i, cell in enumerate(row_data):
                                if i < len(headers) and str(cell).strip():
                                    simple_dict[f'col_{i}'] = str(cell).strip()

                            if simple_dict:
                                row_result = self.process_row_data(simple_dict, row_index, task)
                            else:
                                continue
                        else:
                            continue

                    # تحديث الإحصائيات فقط إذا كان هناك نتيجة
                    if row_result:
                        stats['processed_rows'] += 1
                        stats['customers_created'] += row_result.get('customers_created', 0)
                        stats['customers_updated'] += row_result.get('customers_updated', 0)
                        stats['orders_created'] += row_result.get('orders_created', 0)
                        stats['orders_updated'] += row_result.get('orders_updated', 0)
                        stats['inspections_created'] += row_result.get('inspections_created', 0)
                        stats['installations_created'] += row_result.get('installations_created', 0)

                        if row_result.get('warnings'):
                            stats['warnings'].extend(row_result['warnings'])

                        # طباعة تفاصيل الصف للتشخيص
                        if row_result.get('customers_created', 0) > 0 or row_result.get('orders_created', 0) > 0:
                            print(f'الصف {row_index}: عملاء={row_result.get("customers_created", 0)}, طلبات={row_result.get("orders_created", 0)}')

                except Exception as row_error:
                    error_msg = f'خطأ في الصف {row_index}: {str(row_error)}'
                    stats['errors'].append(error_msg)
                    print(f'خطأ في معالجة الصف {row_index}: {str(row_error)}')

            # تحديث آخر صف تمت معالجته
            self.mapping.last_row_processed = self.mapping.start_row + len(data_rows) - 1
            self.mapping.save(update_fields=['last_row_processed'])

            return {
                'success': True,
                'stats': stats,
                'conflicts': 0
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في معالجة البيانات: {str(e)}'
            }

    def map_row_to_fields(self, headers, row_data, row_index):
        """
        تحويل صف البيانات إلى قاموس باستخدام تعيينات الأعمدة بناءً على رقم العمود أو اسم العمود
        """
        try:
            mapped_data = {}

            if not row_data or all(str(cell).strip() == '' for cell in row_data):
                return None  # صف فارغ

            # معالجة كل عمود
            for col_index, cell_value in enumerate(row_data):
                # جرب أولاً التعيين برقم العمود
                field_type = self.mapping.get_column_mapping(col_index)
                # إذا لم يوجد تعيين برقم العمود، جرب باسم العمود من headers
                if not field_type and headers and col_index < len(headers):
                    field_type = self.mapping.get_column_mapping(headers[col_index])
                if field_type and field_type != 'ignore':
                    # إذا كان الحقل يمثل تاريخًا، مرره على parse_date
                    if field_type in ['order_date', 'inspection_date', 'installation_date', 'created_at', 'updated_at']:
                        cleaned_value = self.clean_cell_value(cell_value, field_type)
                        mapped_data[field_type] = self.parse_date(cleaned_value) if cleaned_value else None
                    else:
                        mapped_data[field_type] = self.clean_cell_value(cell_value, field_type)

            # طباعة القيم التي تم تعيينها للتشخيص
            print(f'صف {row_index} - البيانات المعينة: {mapped_data}')

            return mapped_data if mapped_data else None

        except Exception as e:
            print(f'خطأ في تعيين الصف {row_index}: {str(e)}')
            return None

    def process_order_data(self, row_dict, customer, row_index, force_create=False):
        """
        معالجة بيانات الطلب
        إذا كان force_create=True سيتم إنشاء طلب جديد دائماً.
        """
        try:
            from orders.models import Order

            order_data = {}
            # المبلغ المدفوع
            if 'paid_amount' in row_dict:
                order_data['paid_amount'] = row_dict['paid_amount']
            # عدد النوافذ
            if 'windows_count' in row_dict:
                order_data['windows_count'] = row_dict['windows_count']
            # تاريخ الطلب
            if 'order_date' in row_dict:
                parsed_order_date = self.parse_date(row_dict['order_date'])
                if parsed_order_date:
                    order_data['order_date'] = parsed_order_date
            elif self.mapping.use_current_date_as_created:
                from datetime import datetime
                order_data['order_date'] = datetime.now().date()
            # الفرع
            if self.mapping.default_branch:
                order_data['branch'] = self.mapping.default_branch
            # --- إضافة الحقول المميزة للبحث ---
            for key in ['order_number', 'invoice_number', 'contract_number']:
                if key in row_dict and row_dict[key]:
                    order_data[key] = row_dict[key]
            # فقط نتأكد من وجود عميل
            if not customer:
                return None
            # لوج تشخيصي للقيم المستخدمة في البحث
            print(f"[SYNC][Order Search] order_number={order_data.get('order_number')}, invoice_number={order_data.get('invoice_number')}, contract_number={order_data.get('contract_number')}, customer={customer}")
            # إذا كان force_create=True أنشئ دائماً طلب جديد
            created = False
            if force_create:
                order_data['customer'] = customer
                order = Order.objects.create(**order_data)
                created = True
                # إعادة تحميل الطلب من قاعدة البيانات بعد الحفظ
                from orders.models import Order as OrderModel
                try:
                    order = OrderModel.objects.get(pk=order.pk)
                    order.refresh_from_db()
                    if order.pk and OrderModel.objects.filter(pk=order.pk).exists():
                        if hasattr(order, 'calculate_final_price'):
                            order.calculate_final_price()
                        else:
                            print(f"Order instance has no calculate_final_price method, skipping final price calculation.")
                    else:
                        print(f"Order instance with pk={order.pk} not found in DB, skipping final price calculation.")
                except Exception as calc_err:
                    import traceback
                    print(f"Error calculating final price (create): {calc_err}\n{traceback.format_exc()}")
            else:
                # البحث الذكي عن الطلب الموجود (كما كان سابقاً)
                order = None
                if 'order_number' in order_data and order_data['order_number']:
                    order = Order.objects.filter(order_number=order_data['order_number']).first()
                if not order and 'invoice_number' in order_data and order_data['invoice_number']:
                    order = Order.objects.filter(invoice_number=order_data['invoice_number'], customer=customer).first()
                if not order and 'contract_number' in order_data and order_data['contract_number']:
                    order = Order.objects.filter(contract_number=order_data['contract_number'], customer=customer).first()
                if not order and order_data.get('order_date'):
                    order = Order.objects.filter(customer=customer, order_date=order_data['order_date']).first()
                if order:
                    if self.mapping.update_existing_orders:
                        for field, value in order_data.items():
                            if value and field != 'customer':
                                setattr(order, field, value)
                        order.save()
                        from orders.models import Order as OrderModel
                        try:
                            order = OrderModel.objects.get(pk=order.pk)
                            order.refresh_from_db()
                            if order.pk and OrderModel.objects.filter(pk=order.pk).exists():
                                if hasattr(order, 'calculate_final_price'):
                                    order.calculate_final_price()
                                else:
                                    print(f"Order instance has no calculate_final_price method, skipping final price calculation.")
                            else:
                                print(f"Order instance with pk={order.pk} not found in DB, skipping final price calculation.")
                        except Exception as calc_err:
                            import traceback
                            print(f"Error calculating final price (update): {calc_err}\n{traceback.format_exc()}")
                else:
                    if self.mapping.auto_create_orders:
                        order_data['customer'] = customer
                        order = Order.objects.create(**order_data)
                        created = True
                        from orders.models import Order as OrderModel
                        try:
                            order = OrderModel.objects.get(pk=order.pk)
                            order.refresh_from_db()
                            if order.pk and OrderModel.objects.filter(pk=order.pk).exists():
                                if hasattr(order, 'calculate_final_price'):
                                    order.calculate_final_price()
                                else:
                                    print(f"Order instance has no calculate_final_price method, skipping final price calculation.")
                            else:
                                print(f"Order instance with pk={order.pk} not found in DB, skipping final price calculation.")
                        except Exception as calc_err:
                            import traceback
                            print(f"Error calculating final price (create): {calc_err}\n{traceback.format_exc()}")
            return {
                'instance': order,
                'created': created
            } if order else None
        except Exception as e:
            print(f'خطأ في معالجة بيانات الطلب في الصف {row_index}: {str(e)}')
            return None

    def process_inspection_data(self, row_dict, order, row_index):
        """
        معالجة بيانات المعاينة
        """
        try:
            # التحقق من وجود تاريخ المعاينة
            if 'inspection_date' not in row_dict or not row_dict['inspection_date']:
                return None
            # تمرير تاريخ المعاينة على parse_date
            parsed_inspection_date = self.parse_date(row_dict['inspection_date'])
            if not parsed_inspection_date:
                return None
            # هنا يمكن إضافة معالجة المعاينة إذا كان لديك نموذج Inspection
            # from inspections.models import Inspection
            return None
        except Exception as e:
            print(f'خطأ في معالجة بيانات المعاينة في الصف {row_index}: {str(e)}')
            return None

    def clean_cell_value(self, value, field_type=None):
        """
        تنظيف قيمة الخلية: إزالة الفراغات من البداية والنهاية فقط، وإرجاع القيمة كما هي.
        """
        if isinstance(value, str):
            return value.strip()
        return value

    def parse_date(self, value):
        """
        تحويل التاريخ من أي صيغة شائعة (DD-MM-YYYY أو DD/MM/YYYY أو YYYY-MM-DD) إلى كائن تاريخ أو None.
        """
        from datetime import datetime
        if not value or not str(value).strip():
            return None
        value = str(value).strip()
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except Exception:
                continue
        # إذا لم تنجح أي صيغة، أرجع None
        return None

    def process_row_data(self, row_dict, row_index, task):
        """
        معالجة صف واحد: عميل + طلب + معاينة + تركيب (حسب الإعدادات)
        منطق العميل:
        - إذا وُجد عميل بنفس الاسم فقط (حتى لو رقم الهاتف مختلف):
            - إذا كان رقم الهاتف في الصف الجديد مختلف عن أي عميل بنفس الاسم → يتم إنشاء عميل جديد.
            - إذا كان رقم الهاتف في الصف الجديد مطابق لأحد العملاء بنفس الاسم → استخدم العميل الموجود.
            - إذا كان رقم الهاتف في الصف الجديد فارغ → يتم إنشاء عميل جديد دائمًا.
        - إذا لم يوجد عميل بنفس الاسم: يتم إنشاء عميل جديد.
        """
        stats = {
            'customers_created': 0,
            'customers_updated': 0,
            'orders_created': 0,
            'orders_updated': 0,
            'inspections_created': 0,
            'installations_created': 0,
            'warnings': []
        }
        customer = None
        order = None
        try:
            from customers.models import Customer
            customer = None
            found_by = None
            # طباعة محتوى الصف وقاموس البيانات الناتج للتشخيص
            print(f"[SYNC][DEBUG] Row {row_index} raw dict: {row_dict}")
            logger.info(f"[SYNC][DEBUG] Row {row_index} raw dict: {row_dict}")
            name = row_dict.get('customer_name', '').strip() if 'customer_name' in row_dict else ''
            phone = row_dict.get('customer_phone', '').strip() if 'customer_phone' in row_dict else ''
            if name:
                customers_qs = Customer.objects.filter(name=name)
                if not customers_qs.exists():
                    # لا يوجد عميل بنفس الاسم: أنشئ عميل جديد
                    customer = Customer.objects.create(
                        name=name,
                        phone=phone,
                        customer_type=self.mapping.default_customer_type if self.mapping.default_customer_type else None,
                        category=self.mapping.default_customer_category if self.mapping.default_customer_category else None,
                        branch=self.mapping.default_branch if self.mapping.default_branch else None
                    )
                    stats['customers_created'] += 1
                    print(f"[SYNC][Customer] Row {row_index}: Created new customer (new name): {customer}")
                    logger.info(f"[SYNC][Customer] Row {row_index}: Created new customer (new name): {customer}")
                else:
                    # يوجد عميل بنفس الاسم
                    if not phone:
                        # الهاتف فارغ: استخدم أول عميل بنفس الاسم
                        customer = customers_qs.first()
                        found_by = 'name_only'
                        print(f"[SYNC][Customer] Row {row_index}: Used first customer with same name (empty phone): {customer}")
                        logger.info(f"[SYNC][Customer] Row {row_index}: Used first customer with same name (empty phone): {customer}")
                    else:
                        customer_exact = customers_qs.filter(phone=phone).first()
                        if customer_exact:
                            customer = customer_exact
                            found_by = 'name+phone'
                            print(f"[SYNC][Customer] Row {row_index}: Used existing customer with same name and phone: {customer}")
                            logger.info(f"[SYNC][Customer] Row {row_index}: Used existing customer with same name and phone: {customer}")
                        else:
                            # الهاتف مختلف: أنشئ عميل جديد
                            customer = Customer.objects.create(
                                name=name,
                                phone=phone,
                                customer_type=self.mapping.default_customer_type if self.mapping.default_customer_type else None,
                                category=self.mapping.default_customer_category if self.mapping.default_customer_category else None,
                                branch=self.mapping.default_branch if self.mapping.default_branch else None
                            )
                            stats['customers_created'] += 1
                            print(f"[SYNC][Customer] Row {row_index}: Created new customer (duplicate name, different phone): {customer}")
                            logger.info(f"[SYNC][Customer] Row {row_index}: Created new customer (duplicate name, different phone): {customer}")
                # معالجة الطلب: ابحث أولاً، إذا لم يوجد أنشئ جديد (لا تكرر الطلبات)
                order_result = None
                if customer:
                    order_result = self.process_order_data(row_dict, customer, row_index, force_create=False)
                if order_result:
                    order = order_result.get('instance')
                    if order_result.get('created'):
                        stats['orders_created'] += 1
                        print(f"[SYNC][Order] Row {row_index}: Created new order: {order}")
                        logger.info(f"[SYNC][Order] Row {row_index}: Created new order: {order}")
                    else:
                        stats['orders_updated'] += 1
                        print(f"[SYNC][Order] Row {row_index}: Updated order: {order}")
                        logger.info(f"[SYNC][Order] Row {row_index}: Updated order: {order}")
                else:
                    print(f"[SYNC][Order] Row {row_index}: No order created or updated.")
                    logger.info(f"[SYNC][Order] Row {row_index}: No order created or updated.")
                # معالجة المعاينة إذا لزم الأمر
                if self.mapping.auto_create_inspections and order:
                    inspection_result = self.process_inspection_data(row_dict, order, row_index)
                    if inspection_result:
                        stats['inspections_created'] += 1
            else:
                # اسم العميل فارغ: تجاهل الصف
                stats['warnings'].append(f"Row {row_index}: customer_name is empty, skipping row.")
                print(f"[SYNC][Customer] Row {row_index}: customer_name is empty, skipping row.")
                logger.info(f"[SYNC][Customer] Row {row_index}: customer_name is empty, skipping row.")
        except Exception as e:
            import traceback
            stats['warnings'].append(f'خطأ في معالجة الصف {row_index}: {str(e)}')
            print(f'[SYNC][ERROR] Row {row_index}: {str(e)}\n{traceback.format_exc()}')
            logger.error(f'[SYNC][ERROR] Row {row_index}: {str(e)}\n{traceback.format_exc()}')
        return stats
