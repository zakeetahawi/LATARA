from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from customers.models import Customer
from accounts.models import User, Branch
from model_utils.tracker import FieldTracker

class InspectionEvaluation(models.Model):
    CRITERIA_CHOICES = [
        ('location', _('الموقع')),
        ('condition', _('الحالة')),
        ('suitability', _('الملاءمة')),
        ('safety', _('السلامة')),
        ('accessibility', _('سهولة الوصول')),
    ]

    RATING_CHOICES = [
        (1, _('ضعيف')),
        (2, _('مقبول')),
        (3, _('جيد')),
        (4, _('جيد جداً')),
        (5, _('ممتاز')),
    ]

    inspection = models.ForeignKey('Inspection', on_delete=models.CASCADE, related_name='evaluations', verbose_name=_('المعاينة'))
    criteria = models.CharField(_('معيار التقييم'), max_length=20, choices=CRITERIA_CHOICES)
    rating = models.IntegerField(_('التقييم'), choices=RATING_CHOICES)
    notes = models.TextField(_('ملاحظات التقييم'), blank=True)
    created_at = models.DateTimeField(_('تاريخ التقييم'), auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='evaluations_created', verbose_name=_('تم التقييم بواسطة'))

    class Meta:
        verbose_name = _('تقييم المعاينة')
        verbose_name_plural = _('تقييمات المعاينات')
        indexes = [
            models.Index(fields=['inspection'], name='inspection_eval_insp_idx'),
            models.Index(fields=['criteria'], name='inspection_eval_criteria_idx'),
            models.Index(fields=['rating'], name='inspection_eval_rating_idx'),
            models.Index(fields=['created_by'], name='inspection_eval_creator_idx'),
            models.Index(fields=['created_at'], name='inspection_eval_created_idx'),
        ]

    def __str__(self):
        return f"تقييم معاينة {self.inspection.contract_number}"

class InspectionNotification(models.Model):
    TYPE_CHOICES = [
        ('scheduled', _('موعد معاينة')),
        ('reminder', _('تذكير')),
        ('status_change', _('تغيير الحالة')),
        ('evaluation', _('تقييم جديد')),
    ]

    inspection = models.ForeignKey('Inspection', on_delete=models.CASCADE, related_name='notifications', verbose_name=_('المعاينة'))
    type = models.CharField(_('نوع التنبيه'), max_length=20, choices=TYPE_CHOICES)
    message = models.TextField(_('نص التنبيه'))
    is_read = models.BooleanField(_('تم القراءة'), default=False)
    created_at = models.DateTimeField(_('تاريخ التنبيه'), auto_now_add=True)
    scheduled_for = models.DateTimeField(_('موعد التنبيه'), null=True, blank=True)

    class Meta:
        verbose_name = _('تنبيه معاينة')
        verbose_name_plural = _('تنبيهات المعاينات')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['inspection'], name='inspection_notif_insp_idx'),
            models.Index(fields=['type'], name='inspection_notif_type_idx'),
            models.Index(fields=['is_read'], name='inspection_notif_read_idx'),
            models.Index(fields=['created_at'], name='inspection_notif_created_idx'),
            models.Index(fields=['scheduled_for'], name='inspection_notif_scheduled_idx'),
        ]

    def __str__(self):
        return f"تنبيه: {self.message[:50]}..."

    @property
    def is_scheduled(self):
        return bool(self.scheduled_for)

class InspectionReport(models.Model):
    REPORT_TYPE_CHOICES = [
        ('daily', _('يومي')),
        ('weekly', _('أسبوعي')),
        ('monthly', _('شهري')),
        ('custom', _('مخصص')),
    ]

    title = models.CharField(_('عنوان التقرير'), max_length=200)
    report_type = models.CharField(_('نوع التقرير'), max_length=10, choices=REPORT_TYPE_CHOICES)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='inspection_reports', verbose_name=_('الفرع'))
    date_from = models.DateField(_('من تاريخ'))
    date_to = models.DateField(_('إلى تاريخ'))
    total_inspections = models.IntegerField(_('إجمالي المعاينات'), default=0)
    successful_inspections = models.IntegerField(_('المعاينات الناجحة'), default=0)
    pending_inspections = models.IntegerField(_('المعاينات المعلقة'), default=0)
    cancelled_inspections = models.IntegerField(_('المعاينات الملغاة'), default=0)
    notes = models.TextField(_('ملاحظات'), blank=True)
    created_at = models.DateTimeField(_('تاريخ إنشاء التقرير'), auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='inspection_reports_created', verbose_name=_('تم الإنشاء بواسطة'))

    class Meta:
        verbose_name = _('تقرير معاينات')
        verbose_name_plural = _('تقارير المعاينات')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['report_type'], name='inspection_report_type_idx'),
            models.Index(fields=['branch'], name='inspection_report_branch_idx'),
            models.Index(fields=['date_from'], name='inspection_report_from_idx'),
            models.Index(fields=['date_to'], name='inspection_report_to_idx'),
            models.Index(fields=['created_at'], name='inspection_report_created_idx'),
            models.Index(fields=['created_by'], name='inspection_report_creator_idx'),
        ]

    def __str__(self):
        return f"{self.title} - {self.get_report_type_display()}"

    def calculate_statistics(self):
        from django.core.cache import cache

        # إنشاء مفتاح تخزين مؤقت فريد بناءً على معلمات التقرير
        cache_key = f'inspection_report_stats_{self.branch_id}_{self.date_from}_{self.date_to}'

        # محاولة استرداد النتائج من التخزين المؤقت
        cached_stats = cache.get(cache_key)

        if cached_stats is None:
            # إذا لم تكن النتائج مخزنة مؤقتًا، قم بحساب الإحصائيات من قاعدة البيانات
            inspections = Inspection.objects.filter(
                branch=self.branch,
                request_date__gte=self.date_from,
                request_date__lte=self.date_to
            )
            self.total_inspections = inspections.count()
            self.successful_inspections = inspections.filter(result='passed').count()
            self.pending_inspections = inspections.filter(status='pending').count()
            self.cancelled_inspections = inspections.filter(status='cancelled').count()

            # حفظ النتائج في التخزين المؤقت لمدة ساعة واحدة (3600 ثانية)
            cached_stats = {
                'total': self.total_inspections,
                'successful': self.successful_inspections,
                'pending': self.pending_inspections,
                'cancelled': self.cancelled_inspections
            }
            cache.set(cache_key, cached_stats, 3600)
        else:
            # استخدام النتائج المخزنة مؤقتًا
            self.total_inspections = cached_stats['total']
            self.successful_inspections = cached_stats['successful']
            self.pending_inspections = cached_stats['pending']
            self.cancelled_inspections = cached_stats['cancelled']

        self.save()

class Inspection(models.Model):
    STATUS_CHOICES = [
        ('pending', _('قيد الانتظار')),
        ('scheduled', _('مجدول')),
        ('completed', _('مكتملة')),
        ('cancelled', _('ملغية')),
    ]

    RESULT_CHOICES = [
        ('passed', _('ناجحة')),
        ('failed', _('غير مجدية')),
    ]

    # إضافة متتبع الحقول
    tracker = FieldTracker(fields=['status', 'result'])

    contract_number = models.CharField(_('رقم العقد'), max_length=50, unique=True, blank=True, null=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='inspections',
        verbose_name=_('العميل'),
        null=True,
        blank=True
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name='inspections',
        verbose_name=_('الفرع'),
        null=True,
        blank=True
    )
    inspector = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='assigned_inspections',
        verbose_name=_('المعاين')
    )
    responsible_employee = models.ForeignKey(
        'accounts.Salesperson',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('البائع'),
        related_name='inspections'
    )
    is_from_orders = models.BooleanField(_('من قسم الطلبات'), default=False)
    windows_count = models.IntegerField(_('عدد الشبابيك'), null=True, blank=True)
    inspection_file = models.FileField(_('ملف المعاينة'), upload_to='inspections/files/', null=True, blank=True)
    request_date = models.DateField(_('تاريخ طلب المعاينة'))
    scheduled_date = models.DateField(_('تاريخ تنفيذ المعاينة'))
    status = models.CharField(
        _('الحالة'),
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )
    result = models.CharField(
        _('النتيجة'),
        max_length=10,
        choices=RESULT_CHOICES,
        null=True,
        blank=True
    )
    notes = models.TextField(_('ملاحظات'), blank=True)
    order_notes = models.TextField(_('ملاحظات الطلب'), blank=True, help_text=_('نسخة ثابتة من ملاحظات الطلب'))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_inspections',
        verbose_name=_('تم الإنشاء بواسطة')
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inspections',
        verbose_name=_('الطلب المرتبط')
    )
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    completed_at = models.DateTimeField(_('تاريخ الإكتمال'), null=True, blank=True)

    class Meta:
        verbose_name = _('معاينة')
        verbose_name_plural = _('المعاينات')
        ordering = ['-request_date']
        indexes = [
            models.Index(fields=['contract_number'], name='inspection_contract_idx'),
            models.Index(fields=['customer'], name='inspection_customer_idx'),
            models.Index(fields=['branch'], name='inspection_branch_idx'),
            models.Index(fields=['inspector'], name='inspection_inspector_idx'),
            models.Index(fields=['status'], name='inspection_status_idx'),
            models.Index(fields=['result'], name='inspection_result_idx'),
            models.Index(fields=['request_date'], name='inspection_req_date_idx'),
            models.Index(fields=['scheduled_date'], name='inspection_sched_date_idx'),
            models.Index(fields=['order'], name='inspection_order_idx'),
            models.Index(fields=['created_at'], name='inspection_created_idx'),
        ]

    def __str__(self):
        customer_name = self.customer.name if self.customer else 'عميل جديد'
        return f"{self.contract_number} - {customer_name}"

    def clean(self):
        # Ensure scheduled date is not before request date
        if self.scheduled_date and self.request_date:
            if self.scheduled_date < self.request_date:
                raise ValidationError(_('تاريخ تنفيذ المعاينة لا يمكن أن يكون قبل تاريخ الطلب'))

        # Only allow users to create inspections in their branch
        if self.created_by and not self.created_by.is_superuser:
            if self.branch != self.created_by.branch:
                raise ValidationError(_('لا يمكنك إضافة معاينات لفرع آخر'))

    def save(self, *args, **kwargs):
        if not self.branch and self.created_by:
            self.branch = self.created_by.branch

        # تتبع التغييرات في حقل status
        status_changed = self.tracker.has_changed('status')
        old_status = self.tracker.previous('status')

        # Set completed_at when status changes to completed
        if status_changed and self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()
        elif status_changed and old_status == 'completed' and self.status != 'completed':
            self.completed_at = None

        # نسخ ملاحظات الطلب إلى الحقل الجديد إذا كان الطلب موجودًا
        if self.order and self.order.notes and not self.order_notes:
            self.order_notes = self.order.notes

        super().save(*args, **kwargs)

    def get_status_color(self):
        status_colors = {
            'pending': 'warning',
            'scheduled': 'info',
            'completed': 'success',
            'cancelled': 'danger'
        }
        return status_colors.get(self.status, 'secondary')

    @property
    def is_scheduled(self):
        return self.status == 'scheduled'

    @property
    def is_pending(self):
        return self.status == 'pending'

    @property
    def is_completed(self):
        return self.status == 'completed'

    @property
    def is_cancelled(self):
        return self.status == 'cancelled'

    @property
    def is_successful(self):
        return self.result == 'passed'

    @property
    def is_overdue(self):
        return self.status == 'pending' and self.scheduled_date < timezone.now().date()
