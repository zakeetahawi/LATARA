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


class GoogleSheetMapping(models.Model):
    """
    نموذج تعيين أعمدة Google Sheets إلى حقول النظام
    Maps Google Sheets columns to system fields
    """

    FIELD_TYPES = [
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

    name = models.CharField(_('اسم التعيين'), max_length=100)
    spreadsheet_id = models.CharField(_('معرف جدول البيانات'), max_length=255)
    sheet_name = models.CharField(_('اسم الصفحة'), max_length=100)

    # تعيين الأعمدة
    column_mappings = models.JSONField(
        _('تعيين الأعمدة'),
        default=dict,
        help_text=_('تعيين أعمدة Google Sheets إلى حقول النظام')
    )

    # إعدادات المزامنة
    auto_create_customers = models.BooleanField(_('إنشاء العملاء تلقائياً'), default=True)
    auto_create_orders = models.BooleanField(_('إنشاء الطلبات تلقائياً'), default=True)
    auto_create_inspections = models.BooleanField(_('إنشاء المعاينات تلقائياً'), default=True)
    auto_create_installations = models.BooleanField(_('إنشاء التركيبات تلقائياً'), default=False)

    # إعدادات التحديث
    update_existing_customers = models.BooleanField(_('تحديث العملاء الموجودين'), default=True)
    update_existing_orders = models.BooleanField(_('تحديث الطلبات الموجودة'), default=True)

    # إعدادات المزامنة العكسية
    enable_reverse_sync = models.BooleanField(_('تفعيل المزامنة العكسية'), default=False)
    reverse_sync_fields = models.JSONField(
        _('حقول المزامنة العكسية'),
        default=list,
        help_text=_('الحقول التي سيتم مزامنتها عكسياً إلى Google Sheets')
    )

    # القيم الافتراضية للحقول المفقودة
    default_customer_category = models.ForeignKey(
        'customers.CustomerCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('تصنيف العميل الافتراضي'),
        help_text=_('التصنيف الذي سيتم تعيينه للعملاء الجدد إذا لم يكن محدد في الجدول')
    )
    default_customer_type = models.CharField(
        _('نوع العميل الافتراضي'),
        max_length=20,
        choices=[
            ('retail', _('أفراد')),
            ('wholesale', _('جملة')),
            ('corporate', _('شركات')),
        ],
        null=True,
        blank=True,
        help_text=_('نوع العميل الذي سيتم تعيينه للعملاء الجدد إذا لم يكن محدد في الجدول')
    )
    default_branch = models.ForeignKey(
        'accounts.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('الفرع الافتراضي'),
        help_text=_('الفرع الذي سيتم تعيينه للعملاء والطلبات الجديدة إذا لم يكن محدد في الجدول')
    )
    use_current_date_as_created = models.BooleanField(
        _('استخدام التاريخ الحالي كتاريخ الإضافة'),
        default=True,
        help_text=_('استخدام تاريخ المزامنة كتاريخ إضافة للسجلات الجديدة')
    )

    # إعدادات الصفوف
    header_row = models.IntegerField(_('صف العناوين'), default=1)
    start_row = models.IntegerField(_('صف البداية'), default=2)

    # حالة التعيين
    is_active = models.BooleanField(_('نشط'), default=True)
    last_sync = models.DateTimeField(_('آخر مزامنة'), null=True, blank=True)
    last_row_processed = models.IntegerField(_('آخر صف تمت معالجته'), default=0)

    # معلومات النظام
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('تم الإنشاء بواسطة')
    )

    class Meta:
        verbose_name = _('تعيين Google Sheets')
        verbose_name_plural = _('تعيينات Google Sheets')
        ordering = ['-created_at']
        unique_together = ['spreadsheet_id', 'sheet_name']

    def __str__(self):
        return f"{self.name} - {self.sheet_name}"

    def get_clean_column_mappings(self):
        """
        إرجاع تعيينات الأعمدة مع تنظيف أسماء الأعمدة
        Return column mappings with cleaned column names
        """
        if not self.column_mappings:
            return {}

        cleaned_mappings = {}
        for column, field_type in self.column_mappings.items():
            # تنظيف اسم العمود
            cleaned_column = self._clean_column_name(column)
            # ترجمة نوع الحقل
            translated_type = self._translate_field_type(field_type)
            cleaned_mappings[cleaned_column] = translated_type

        return cleaned_mappings

    def _clean_column_name(self, column_name):
        """
        تنظيف اسم العمود من الأحرف غير المرغوبة
        Clean column name from unwanted characters
        """
        if not column_name:
            return ""

        import html
        import unicodedata

        try:
            # فك تشفير HTML entities
            if '&#' in str(column_name) or '&' in str(column_name):
                column_name = html.unescape(str(column_name))

            # تطبيع النص العربي
            column_name = unicodedata.normalize('NFKC', str(column_name))

            # إزالة الأحرف غير المرئية
            unwanted_chars = ['\u200c', '\u200d', '\u200e', '\u200f', '\ufeff']
            for char in unwanted_chars:
                column_name = column_name.replace(char, '')

            # تنظيف المسافات
            column_name = ' '.join(column_name.split())

            return column_name.strip()

        except Exception:
            return str(column_name)

    def _translate_field_type(self, field_type):
        """
        ترجمة نوع الحقل إلى العربية
        Translate field type to Arabic
        """
        translations = {
            'customer_name': 'اسم العميل',
            'customer_phone': 'رقم الهاتف',
            'customer_email': 'البريد الإلكتروني',
            'customer_address': 'العنوان',
            'order_number': 'رقم الطلب',
            'invoice_number': 'رقم الفاتورة',
            'contract_number': 'رقم العقد',
            'total_amount': 'المبلغ الإجمالي',
            'paid_amount': 'المبلغ المدفوع',
            'order_status': 'حالة الطلب',
            'order_date': 'تاريخ الطلب',
            'delivery_date': 'تاريخ التسليم',
            'notes': 'ملاحظات',
            'salesperson': 'البائع',
            'branch': 'الفرع',
            'product_type': 'نوع المنتج',
            'quantity': 'الكمية',
            'unit_price': 'سعر الوحدة',
            'discount': 'الخصم',
            'tax': 'الضريبة',
            'ignore': 'تجاهل',
        }

        return translations.get(str(field_type), str(field_type))

    def get_column_mapping(self, column_index_or_name):
        """الحصول على تعيين عمود معين"""
        mappings = self.column_mappings or {}
        return mappings.get(str(column_index_or_name))

    def set_column_mapping(self, column_index_or_name, field_type):
        """تعيين عمود إلى نوع حقل"""
        if not self.column_mappings:
            self.column_mappings = {}
        self.column_mappings[str(column_index_or_name)] = field_type

    def get_mapped_fields(self):
        """الحصول على قائمة الحقول المعينة"""
        mappings = self.column_mappings or {}
        return [field for field in mappings.values() if field != 'ignore']

    def validate_mappings(self):
        """التحقق من صحة التعيينات"""
        errors = []
        mappings = self.column_mappings or {}

        # التحقق من وجود الحقول الأساسية
        required_fields = ['customer_name']
        mapped_fields = list(mappings.values())

        for field in required_fields:
            if field not in mapped_fields:
                errors.append(f"الحقل المطلوب '{field}' غير معين")

        # التحقق من عدم تكرار التعيينات
        field_counts = {}
        for field in mapped_fields:
            if field != 'ignore':
                field_counts[field] = field_counts.get(field, 0) + 1

        for field, count in field_counts.items():
            if count > 1:
                errors.append(f"الحقل '{field}' معين أكثر من مرة")

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
        ('data_mismatch', _('عدم تطابق البيانات')),
        ('concurrent_edit', _('تعديل متزامن')),
        ('missing_record', _('سجل مفقود')),
        ('validation_error', _('خطأ في التحقق')),
    ]

    RESOLUTION_STATUS = [
        ('pending', _('في الانتظار')),
        ('resolved_system', _('تم الحل لصالح النظام')),
        ('resolved_sheet', _('تم الحل لصالح Google Sheets')),
        ('resolved_manual', _('تم الحل يدوياً')),
        ('ignored', _('تم التجاهل')),
    ]

    task = models.ForeignKey(
        GoogleSyncTask,
        on_delete=models.CASCADE,
        related_name='conflicts',
        verbose_name=_('مهمة المزامنة')
    )

    conflict_type = models.CharField(_('نوع التعارض'), max_length=20, choices=CONFLICT_TYPES)
    resolution_status = models.CharField(_('حالة الحل'), max_length=20, choices=RESOLUTION_STATUS, default='pending')

    # معلومات السجل
    record_type = models.CharField(_('نوع السجل'), max_length=50)  # customer, order, etc.
    record_id = models.CharField(_('معرف السجل'), max_length=100, blank=True)
    sheet_row = models.IntegerField(_('رقم الصف في الجدول'))

    # بيانات التعارض
    system_data = models.JSONField(_('بيانات النظام'), default=dict)
    sheet_data = models.JSONField(_('بيانات Google Sheets'), default=dict)

    # تفاصيل التعارض
    conflict_description = models.TextField(_('وصف التعارض'))
    resolution_notes = models.TextField(_('ملاحظات الحل'), blank=True)

    # معلومات النظام
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    resolved_at = models.DateTimeField(_('تاريخ الحل'), null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('تم الحل بواسطة')
    )

    class Meta:
        verbose_name = _('تعارض مزامنة')
        verbose_name_plural = _('تعارضات المزامنة')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_conflict_type_display()} - صف {self.sheet_row}"

    def resolve_conflict(self, resolution_status, resolved_by, notes=""):
        """حل التعارض"""
        self.resolution_status = resolution_status
        self.resolved_by = resolved_by
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        self.save(update_fields=['resolution_status', 'resolved_by', 'resolved_at', 'resolution_notes'])

    def get_conflict_summary(self):
        """ملخص التعارض"""
        return {
            'type': self.get_conflict_type_display(),
            'record_type': self.record_type,
            'row': self.sheet_row,
            'description': self.conflict_description,
            'status': self.get_resolution_status_display()
        }


class GoogleSyncSchedule(models.Model):
    """
    نموذج جدولة المزامنة التلقائية
    Automatic Sync Schedule Model
    """

    FREQUENCY_CHOICES = [
        (1, _('كل دقيقة')),
        (5, _('كل 5 دقائق')),
        (15, _('كل 15 دقيقة')),
        (30, _('كل 30 دقيقة')),
        (60, _('كل ساعة')),
        (360, _('كل 6 ساعات')),
        (720, _('كل 12 ساعة')),
        (1440, _('يومياً')),
    ]

    mapping = models.OneToOneField(
        GoogleSheetMapping,
        on_delete=models.CASCADE,
        related_name='schedule',
        verbose_name=_('تعيين الصفحة')
    )

    is_active = models.BooleanField(_('نشط'), default=False)
    frequency_minutes = models.IntegerField(_('التكرار (بالدقائق)'), choices=FREQUENCY_CHOICES, default=60)

    # إعدادات التشغيل
    last_run = models.DateTimeField(_('آخر تشغيل'), null=True, blank=True)
    next_run = models.DateTimeField(_('التشغيل القادم'), null=True, blank=True)

    # إحصائيات
    total_runs = models.IntegerField(_('إجمالي مرات التشغيل'), default=0)
    successful_runs = models.IntegerField(_('مرات التشغيل الناجحة'), default=0)
    failed_runs = models.IntegerField(_('مرات التشغيل الفاشلة'), default=0)

    # معلومات النظام
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_('تم الإنشاء بواسطة')
    )

    class Meta:
        verbose_name = _('جدولة المزامنة')
        verbose_name_plural = _('جدولة المزامنة')
        ordering = ['-created_at']

    def __str__(self):
        return f"جدولة {self.mapping.name} - كل {self.frequency_minutes} دقيقة"

    def calculate_next_run(self):
        """حساب موعد التشغيل القادم"""
        if not self.last_run:
            self.next_run = timezone.now()
        else:
            self.next_run = self.last_run + timezone.timedelta(minutes=self.frequency_minutes)
        self.save(update_fields=['next_run'])
        return self.next_run

    def is_due(self):
        """التحقق من حان وقت التشغيل"""
        if not self.is_active:
            return False
        if not self.next_run:
            self.calculate_next_run()
        return timezone.now() >= self.next_run

    def record_run(self, success=True):
        """تسجيل تشغيل المهمة"""
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
        تحويل صف البيانات إلى قاموس باستخدام تعيينات الأعمدة
        """
        try:
            mapped_data = {}

            # التأكد من أن الصف يحتوي على بيانات
            if not row_data or all(not str(cell).strip() for cell in row_data):
                return None  # صف فارغ

            # معالجة كل عمود
            for col_index, header in enumerate(headers):
                if col_index < len(row_data):
                    cell_value = row_data[col_index]

                    # التحقق من وجود تعيين لهذا العمود
                    if header in self.mapping.column_mappings:
                        field_type = self.mapping.column_mappings[header]

                        # تجاهل الأعمدة المحددة للتجاهل
                        if field_type == 'ignore':
                            continue

                        # تنظيف وتحويل قيمة الخلية
                        cleaned_value = self.clean_cell_value(cell_value, field_type)

                        if cleaned_value is not None:
                            mapped_data[field_type] = cleaned_value

            return mapped_data if mapped_data else None

        except Exception as e:
            print(f'خطأ في تعيين الصف {row_index}: {str(e)}')
            return None

    def clean_cell_value(self, value, field_type):
        """
        تنظيف وتحويل قيمة الخلية حسب نوع الحقل
        """
        if value is None or str(value).strip() == '':
            return None

        value_str = str(value).strip()

        # تنظيف حسب نوع الحقل
        if field_type in ['customer_phone', 'customer_phone2']:
            # تنظيف أرقام الهاتف
            import re
            phone = re.sub(r'[^0-9+]', '', value_str)
            return phone if phone else None

        elif field_type in ['total_amount', 'paid_amount']:
            # تحويل المبالغ إلى أرقام
            try:
                import re
                amount_str = re.sub(r'[^0-9.]', '', value_str)
                return float(amount_str) if amount_str else 0.0
            except:
                return 0.0

        elif field_type in ['windows_count']:
            # تحويل العدد إلى رقم صحيح
            try:
                return int(float(value_str))
            except:
                return 0

        elif field_type in ['order_date', 'inspection_date']:
            # تحويل التاريخ
            return self.parse_date(value_str)

        else:
            # نص عادي
            return value_str

    def parse_date(self, date_str):
        """
        تحويل نص التاريخ إلى كائن تاريخ
        """
        if not date_str:
            return None

        try:
            from datetime import datetime
            import re

            # أنماط التاريخ المختلفة
            date_patterns = [
                '%Y-%m-%d',
                '%d/%m/%Y',
                '%m/%d/%Y',
                '%d-%m-%Y',
                '%Y/%m/%d',
                '%d.%m.%Y'
            ]

            # تنظيف النص
            clean_date = re.sub(r'[^0-9/.-]', '', date_str.strip())

            for pattern in date_patterns:
                try:
                    return datetime.strptime(clean_date, pattern).date()
                except ValueError:
                    continue

            # إذا فشل جميع الأنماط، استخدم التاريخ الحالي
            if self.mapping.use_current_date_as_created:
                return datetime.now().date()

            return None

        except Exception as e:
            print(f'خطأ في تحويل التاريخ {date_str}: {str(e)}')
            return None

    def process_row_data(self, row_dict, row_index, task):
        """
        معالجة بيانات الصف وإنشاء/تحديث السجلات
        """
        result = {
            'customers_created': 0,
            'customers_updated': 0,
            'orders_created': 0,
            'orders_updated': 0,
            'inspections_created': 0,
            'installations_created': 0,
            'warnings': []
        }

        try:
            # معالجة بيانات العميل
            customer = self.process_customer_data(row_dict, row_index)
            if customer:
                if customer.get('created'):
                    result['customers_created'] += 1
                else:
                    result['customers_updated'] += 1

            # معالجة بيانات الطلب
            if customer and customer.get('instance'):
                order = self.process_order_data(row_dict, customer['instance'], row_index)
                if order:
                    if order.get('created'):
                        result['orders_created'] += 1
                    else:
                        result['orders_updated'] += 1

                # معالجة بيانات المعاينة
                if order and order.get('instance'):
                    inspection = self.process_inspection_data(row_dict, order['instance'], row_index)
                    if inspection and inspection.get('created'):
                        result['inspections_created'] += 1

                    # معالجة بيانات التركيب
                    installation = self.process_installation_data(row_dict, order['instance'], row_index)
                    if installation and installation.get('created'):
                        result['installations_created'] += 1

            return result

        except Exception as e:
            result['warnings'].append(f'خطأ في معالجة الصف {row_index}: {str(e)}')
            return result

    def process_customer_data(self, row_dict, row_index):
        """
        معالجة بيانات العميل
        """
        try:
            from customers.models import Customer, CustomerCategory
            from accounts.models import Branch

            # الحقول المطلوبة للعميل
            customer_data = {}

            # اسم العميل
            if 'customer_name' in row_dict and row_dict['customer_name']:
                customer_data['name'] = row_dict['customer_name']

            # رقم الهاتف
            if 'customer_phone' in row_dict and row_dict['customer_phone']:
                customer_data['phone'] = row_dict['customer_phone']

            if 'customer_phone2' in row_dict and row_dict['customer_phone2']:
                customer_data['phone2'] = row_dict['customer_phone2']

            # العنوان
            if 'customer_address' in row_dict and row_dict['customer_address']:
                customer_data['address'] = row_dict['customer_address']

            # إضافة حقول أخرى من الجدول
            field_mappings = {
                'salesperson': 'salesperson',
                'notes': 'notes',
                'contract_number': 'contract_number',
                'invoice_number': 'invoice_number',
                'order_status': 'status'
            }

            for sheet_field, customer_field in field_mappings.items():
                if sheet_field in row_dict and row_dict[sheet_field]:
                    customer_data[customer_field] = row_dict[sheet_field]

            # إنشاء عميل حتى لو كانت البيانات ناقصة
            # فقط نتأكد من وجود أي بيانات في الصف
            if not customer_data:
                # إذا لم تكن هناك بيانات معينة، حاول استخراج بيانات من أي حقل
                for key, value in row_dict.items():
                    if value and str(value).strip():
                        # استخدم أول قيمة موجودة كاسم عميل
                        customer_data['name'] = f'عميل - {str(value).strip()[:50]}'
                        break

                if not customer_data:
                    return None

            # إذا لم يكن هناك اسم، نضع اسم افتراضي
            if not customer_data.get('name'):
                if customer_data.get('phone'):
                    customer_data['name'] = f'عميل - {customer_data["phone"]}'
                elif customer_data.get('contract_number'):
                    customer_data['name'] = f'عميل - عقد {customer_data["contract_number"]}'
                else:
                    customer_data['name'] = f'عميل - صف {row_index}'

            # البحث عن عميل موجود
            customer = None
            if customer_data.get('phone'):
                customer = Customer.objects.filter(phone=customer_data['phone']).first()

            if not customer and customer_data.get('name'):
                customer = Customer.objects.filter(name=customer_data['name']).first()

            created = False
            if customer:
                # تحديث العميل الموجود
                if self.mapping.update_existing_customers:
                    for field, value in customer_data.items():
                        if value:
                            setattr(customer, field, value)
                    customer.save()
            else:
                # إنشاء عميل جديد
                if self.mapping.auto_create_customers:
                    # إضافة القيم الافتراضية
                    if self.mapping.default_customer_category:
                        customer_data['category'] = self.mapping.default_customer_category

                    if self.mapping.default_customer_type:
                        customer_data['customer_type'] = self.mapping.default_customer_type

                    if self.mapping.default_branch:
                        customer_data['branch'] = self.mapping.default_branch
                    else:
                        # إذا لم يكن هناك فرع افتراضي، حاول جلب أول فرع
                        try:
                            from accounts.models import Branch
                            first_branch = Branch.objects.first()
                            if first_branch:
                                customer_data['branch'] = first_branch
                        except:
                            pass

                    customer = Customer.objects.create(**customer_data)
                    created = True

            return {
                'instance': customer,
                'created': created
            } if customer else None

        except Exception as e:
            print(f'خطأ في معالجة بيانات العميل في الصف {row_index}: {str(e)}')
            return None

    def process_order_data(self, row_dict, customer, row_index):
        """
        معالجة بيانات الطلب
        """
        try:
            from orders.models import Order

            # الحقول المطلوبة للطلب
            order_data = {
                'customer': customer
            }

            # المبلغ الإجمالي
            if 'total_amount' in row_dict:
                order_data['total_amount'] = row_dict['total_amount']

            # المبلغ المدفوع
            if 'paid_amount' in row_dict:
                order_data['paid_amount'] = row_dict['paid_amount']

            # عدد النوافذ
            if 'windows_count' in row_dict:
                order_data['windows_count'] = row_dict['windows_count']

            # تاريخ الطلب
            if 'order_date' in row_dict:
                order_data['order_date'] = row_dict['order_date']
            elif self.mapping.use_current_date_as_created:
                from datetime import datetime
                order_data['order_date'] = datetime.now().date()

            # الفرع
            if self.mapping.default_branch:
                order_data['branch'] = self.mapping.default_branch

            # إنشاء طلب حتى لو لم تكن هناك مبالغ أو عدد نوافذ
            # فقط نتأكد من وجود عميل
            if not customer:
                return None

            # البحث عن طلب موجود
            order = None
            if order_data.get('order_date'):
                order = Order.objects.filter(
                    customer=customer,
                    order_date=order_data['order_date']
                ).first()

            created = False
            if order:
                # تحديث الطلب الموجود
                if self.mapping.update_existing_orders:
                    for field, value in order_data.items():
                        if value and field != 'customer':
                            setattr(order, field, value)
                    order.save()
            else:
                # إنشاء طلب جديد
                if self.mapping.auto_create_orders:
                    order = Order.objects.create(**order_data)
                    created = True

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

            # هنا يمكن إضافة معالجة المعاينة إذا كان لديك نموذج Inspection
            # from inspections.models import Inspection

            return None

        except Exception as e:
            print(f'خطأ في معالجة بيانات المعاينة في الصف {row_index}: {str(e)}')
            return None

    def process_installation_data(self, row_dict, order, row_index):
        """
        معالجة بيانات التركيب
        """
        try:
            # هنا يمكن إضافة معالجة التركيب إذا كان لديك نموذج Installation
            # from installations.models import Installation

            return None

        except Exception as e:
            print(f'خطأ في معالجة بيانات التركيب في الصف {row_index}: {str(e)}')
            return None