from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import Branch

User = get_user_model()


def get_customer_types():
    """استرجاع أنواع العملاء من قاعدة البيانات مع تخزين مؤقت"""
    cache_key = 'customer_types_choices'
    cached_types = cache.get(cache_key)
    
    if cached_types is None:
        try:
            from django.apps import apps
            CustomerType = apps.get_model('customers', 'CustomerType')
            
            types = [(t.code, t.name) for t in CustomerType.objects.filter(
                is_active=True).order_by('name')]
            cache.set(cache_key, types, timeout=3600)
            cached_types = types
        except Exception:
            cached_types = [
                ('retail', 'أفراد'),
                ('wholesale', 'جملة'),
                ('corporate', 'شركات'),
            ]
            
    return cached_types or []


class CustomerCategory(models.Model):
    name = models.CharField(_('اسم التصنيف'), max_length=50, db_index=True)
    description = models.TextField(_('وصف التصنيف'), blank=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)

    class Meta:
        verbose_name = _('تصنيف العملاء')
        verbose_name_plural = _('تصنيفات العملاء')
        ordering = ['name']
        indexes = [
            models.Index(fields=['name'], name='customer_cat_name_idx'),
        ]

    def __str__(self):
        return self.name


class CustomerNote(models.Model):
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.CASCADE,
        related_name='notes_history',
        verbose_name=_('العميل')
    )
    note = models.TextField(_('الملاحظة'))
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='customer_notes_created',
        verbose_name=_('تم الإنشاء بواسطة')
    )
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)

    class Meta:
        verbose_name = _('ملاحظة العميل')
        verbose_name_plural = _('ملاحظات العملاء')
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['customer', 'created_at'],
                name='customer_note_idx'
            ),
            models.Index(
                fields=['created_by'],
                name='customer_note_creator_idx'
            ),
        ]

    def __str__(self):
        return (f"{self.customer.name} - "
                f"{self.created_at.strftime('%Y-%m-%d')}")


class CustomerType(models.Model):
    code = models.CharField(_('الرمز'), max_length=20, unique=True)
    name = models.CharField(_('اسم النوع'), max_length=50, db_index=True)
    description = models.TextField(_('وصف النوع'), blank=True)
    is_active = models.BooleanField(_('نشط'), default=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)

    class Meta:
        verbose_name = _('نوع العميل')
        verbose_name_plural = _('أنواع العملاء')
        ordering = ['name']
        indexes = [
            models.Index(fields=['code'], name='customer_type_code_idx'),
            models.Index(fields=['name'], name='customer_type_name_idx'),
        ]

    def __str__(self):
        return self.name


class Customer(models.Model):
    STATUS_CHOICES = [
        ('active', _('نشط')),
        ('inactive', _('غير نشط')),
        ('blocked', _('محظور')),
    ]

    code = models.CharField(
        _('كود العميل'),
        max_length=10,
        unique=True,
        blank=True
    )
    image = models.ImageField(
        _('صورة العميل'),
        upload_to='customers/images/%Y/%m/',
        blank=True,
        null=True
    )
    category = models.ForeignKey(
        CustomerCategory,
        on_delete=models.SET_NULL,        null=True,        blank=True,
        related_name='customers',
        verbose_name=_('تصنيف العميل')
    )
    customer_type = models.CharField(
        _('نوع العميل'),
        max_length=20,
        default='retail'
    )
    name = models.CharField(_('اسم العميل'), max_length=200, db_index=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name='customers',
        verbose_name=_('الفرع'),
        null=True,
        blank=True
    )
    phone = models.CharField(_('رقم الهاتف'), max_length=20, db_index=True)
    phone2 = models.CharField(
        _('رقم الهاتف الثاني'),
        max_length=20,
        blank=True,
        null=True,
        help_text=_('رقم هاتف إضافي اختياري')
    )
    email = models.EmailField(_('البريد الإلكتروني'), blank=True, null=True)
    address = models.TextField(_('العنوان'))
    interests = models.TextField(
        _('اهتمامات العميل'),
        blank=True,
        help_text=_('اكتب اهتمامات العميل وتفضيلاته')
    )
    status = models.CharField(
        _('الحالة'),
        max_length=10,
        choices=STATUS_CHOICES,
        default='active',
        db_index=True
    )
    notes = models.TextField(_('ملاحظات'), blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='customers_created',
        verbose_name=_('تم الإنشاء بواسطة')
    )
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)

    class Meta:
        verbose_name = _('عميل')
        verbose_name_plural = _('سجل العملاء')
        ordering = ['-created_at']
        indexes = [
            # فهارس بسيطة للحقول الأساسية
            models.Index(fields=['code'], name='cust_code_idx'),
            models.Index(fields=['name'], name='cust_name_idx'),
            models.Index(
                fields=['phone', 'phone2'],
                name='cust_phones_idx'
            ),
            models.Index(fields=['email'], name='cust_email_idx'),
            models.Index(fields=['status'], name='cust_status_idx'),
            models.Index(
                fields=['customer_type'],
                name='cust_type_idx'
            ),
            models.Index(
                fields=['created_at'],
                name='cust_created_idx'
            ),
            models.Index(
                fields=['updated_at'],
                name='cust_updated_idx'
            ),
            
            # فهارس مركبة للبحث المتعدد
            models.Index(
                fields=['branch', 'status', 'customer_type'],
                name='cust_br_st_type_idx'
            ),
            models.Index(
                fields=['name', 'phone', 'email'],
                name='cust_search_idx'
            ),
            models.Index(
                fields=['created_by', 'branch'],
                name='cust_creator_branch_idx'
            ),
            
            # فهرس جزئي للعملاء النشطين
            models.Index(
                fields=['name', 'phone'],
                name='cust_active_idx',
                condition=models.Q(status='active')
            ),
        ]
        permissions = [
            ('view_customer_reports', _('Can view customer reports')),
            ('export_customer_data', _('Can export customer data')),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        if self.created_by and not self.created_by.is_superuser:
            if self.branch != self.created_by.branch:
                raise ValidationError(
                    _('لا يمكنك إضافة عملاء لفرع آخر')
                )
        # منع تكرار رقم الهاتف
        if self.phone:
            qs = Customer.objects.filter(phone=self.phone)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({'phone': _('رقم الهاتف مستخدم بالفعل لعميل آخر')})

    def save(self, *args, **kwargs):
        if not self.code:
            latest_customer = Customer.objects.filter(
                branch=self.branch
            ).order_by('-code').first()
            if latest_customer:
                try:
                    sequence = int(latest_customer.code.split('-')[1]) + 1
                except (IndexError, ValueError):
                    sequence = 1
            else:
                sequence = 1
            self.code = f"{self.branch.code}-{str(sequence).zfill(4)}"
        super().save(*args, **kwargs)

    @property
    def branch_code(self):
        """Get the branch code part"""
        return self.code.split('-')[0] if self.code else ''

    @property
    def sequence_number(self):
        """Get the sequence number part"""
        return self.code.split('-')[1] if self.code else ''

    @classmethod
    def get_customer_types(cls):
        """Helper method to get customer types"""
        return get_customer_types()

    def get_customer_type_display(self):
        """عرض نوع العميل بالاسم المقروء"""
        if not self.customer_type:
            return 'غير محدد'
        
        customer_types_dict = dict(get_customer_types())
        return customer_types_dict.get(self.customer_type, self.customer_type)
