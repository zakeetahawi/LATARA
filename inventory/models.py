from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from accounts.models import User, Branch
import uuid
from datetime import datetime
from django.core.validators import MinValueValidator
from django.contrib.auth import get_user_model
from .managers import ProductManager
from django.db.models import Sum

class Category(models.Model):
    """
    Model for product categories
    """
    name = models.CharField(_('اسم الفئة'), max_length=100)
    description = models.TextField(_('الوصف'), blank=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_('الفئة الأب')
    )

    class Meta:
        verbose_name = _('فئة')
        verbose_name_plural = _('الفئات')
        ordering = ['name']

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} - {self.name}"
        return self.name

class Product(models.Model):
    """
    Model for products
    """
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(
        'Category',
        on_delete=models.CASCADE,
        related_name='products',
        verbose_name=_('الفئة'),
        null=True,  # Allow null temporarily for imports
    )
    description = models.TextField(_('الوصف'), blank=True)
    minimum_stock = models.PositiveIntegerField(_('الحد الأدنى للمخزون'), default=0)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)

    # استخدام المدير المخصص
    objects = ProductManager()

    class Meta:
        verbose_name = _('منتج')
        verbose_name_plural = _('منتجات')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['name', 'code']),
            models.Index(fields=['category']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.name

    @property
    def current_stock(self):
        """Get current stock level"""
        stock_in = self.transactions.filter(transaction_type='in').aggregate(Sum('quantity'))['quantity__sum'] or 0
        stock_out = self.transactions.filter(transaction_type='out').aggregate(Sum('quantity'))['quantity__sum'] or 0
        return stock_in - stock_out

    @property
    def needs_restock(self):
        """Check if product needs restocking"""
        return 0 < self.current_stock <= self.minimum_stock

    def save(self, *args, **kwargs):
        # تنظيف ذاكرة التخزين المؤقت عند حفظ المنتج
        from django.core.cache import cache

        # إذا لم يكن هناك فئة، حاول العثور على فئة افتراضية
        if not self.category:
            from django.db import transaction
            try:
                with transaction.atomic():
                    # البحث عن فئة افتراضية
                    default_category = Category.objects.filter(name='عام').first()
                    if not default_category:
                        default_category = Category.objects.first()
                    if default_category:
                        self.category = default_category
                        print(f"Assigned default category '{default_category.name}' to product '{self.name}'")
            except Exception as e:
                print(f"Error assigning default category: {e}")

        # تحديد مفاتيح ذاكرة التخزين المؤقت
        cache_keys = [
            f'product_detail_{self.id}',
            'product_list_all',
            'inventory_dashboard_stats'
        ]

        # إضافة مفاتيح متعلقة بالفئة إذا كانت موجودة
        if self.category_id:
            cache_keys.extend([
                f'category_stats_{self.category_id}',
                f'product_list_{self.category_id}',
            ])

        # حفظ المنتج
        super().save(*args, **kwargs)

        # حذف مفاتيح ذاكرة التخزين المؤقت
        cache.delete_many(cache_keys)

class Supplier(models.Model):
    """
    Model for suppliers
    """
    name = models.CharField(_('اسم المورد'), max_length=200)
    contact_person = models.CharField(_('جهة الاتصال'), max_length=100, blank=True)
    phone = models.CharField(_('رقم الهاتف'), max_length=20, blank=True)
    email = models.EmailField(_('البريد الإلكتروني'), blank=True)
    address = models.TextField(_('العنوان'), blank=True)
    tax_number = models.CharField(_('الرقم الضريبي'), max_length=50, blank=True)
    notes = models.TextField(_('ملاحظات'), blank=True)

    class Meta:
        verbose_name = _('مورد')
        verbose_name_plural = _('الموردين')
        ordering = ['name']

    def __str__(self):
        return self.name

class Warehouse(models.Model):
    """
    Model for warehouses
    """
    name = models.CharField(_('اسم المستودع'), max_length=100)
    code = models.CharField(_('رمز المستودع'), max_length=20, unique=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name='warehouses',
        verbose_name=_('الفرع')
    )
    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_warehouses',
        verbose_name=_('المدير')
    )
    address = models.TextField(_('العنوان'), blank=True)
    is_active = models.BooleanField(_('نشط'), default=True)
    notes = models.TextField(_('ملاحظات'), blank=True)

    class Meta:
        verbose_name = _('مستودع')
        verbose_name_plural = _('المستودعات')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"

class WarehouseLocation(models.Model):
    """
    Model for specific locations within warehouses
    """
    name = models.CharField(_('اسم الموقع'), max_length=100)
    code = models.CharField(_('رمز الموقع'), max_length=30)
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='locations',
        verbose_name=_('المستودع')
    )
    description = models.TextField(_('الوصف'), blank=True)

    class Meta:
        verbose_name = _('موقع مستودع')
        verbose_name_plural = _('مواقع المستودعات')
        ordering = ['warehouse', 'name']
        unique_together = ['warehouse', 'code']

    def __str__(self):
        return f"{self.warehouse.name} - {self.name} ({self.code})"

class ProductBatch(models.Model):
    """
    Model for tracking product batches
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='batches',
        verbose_name=_('المنتج')
    )
    batch_number = models.CharField(_('رقم الدفعة'), max_length=50)
    location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='product_batches',
        verbose_name=_('الموقع')
    )
    quantity = models.PositiveIntegerField(_('الكمية'))
    manufacturing_date = models.DateField(_('تاريخ التصنيع'), null=True, blank=True)
    expiry_date = models.DateField(_('تاريخ الصلاحية'), null=True, blank=True)
    barcode = models.CharField(_('الباركود'), max_length=100, blank=True)
    cost_price = models.DecimalField(_('سعر التكلفة'), max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)

    class Meta:
        verbose_name = _('دفعة منتج')
        verbose_name_plural = _('دفعات المنتجات')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product'], name='batch_product_idx'),
            models.Index(fields=['batch_number'], name='batch_number_idx'),
            models.Index(fields=['expiry_date'], name='batch_expiry_idx'),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.batch_number} ({self.quantity})"

    def save(self, *args, **kwargs):
        # Generate barcode if not provided
        if not self.barcode:
            self.barcode = f"B-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

class StockTransaction(models.Model):
    """
    Model for tracking stock transactions
    """
    TRANSACTION_TYPES = [
        ('in', _('وارد')),
        ('out', _('صادر')),
        ('transfer', _('نقل')),
        ('adjustment', _('تسوية'))
    ]

    REASON_CHOICES = [
        ('purchase', _('شراء')),
        ('sale', _('بيع')),
        ('return', _('مرتجع')),
        ('transfer', _('نقل')),
        ('inventory_check', _('جرد')),
        ('damage', _('تلف')),
        ('production', _('إنتاج')),
        ('other', _('أخرى'))
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='transactions',
        verbose_name=_('المنتج')
    )
    transaction_type = models.CharField(_('نوع الحركة'), max_length=10, choices=TRANSACTION_TYPES)
    reason = models.CharField(_('السبب'), max_length=20, choices=REASON_CHOICES, default='other')
    quantity = models.DecimalField(_('الكمية'), max_digits=10, decimal_places=2)
    reference = models.CharField(_('المرجع'), max_length=100, blank=True)
    date = models.DateTimeField(_('التاريخ'), auto_now_add=True)
    notes = models.TextField(_('ملاحظات'), blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='stock_transactions',
        verbose_name=_('تم بواسطة')
    )

    class Meta:
        verbose_name = _('حركة مخزون')
        verbose_name_plural = _('حركات المخزون')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['product'], name='transaction_product_idx'),
            models.Index(fields=['transaction_type'], name='transaction_type_idx'),
            models.Index(fields=['date'], name='transaction_date_idx'),
        ]

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.product.name} ({self.quantity})"

class PurchaseOrder(models.Model):
    """
    Model for purchase orders
    """
    STATUS_CHOICES = [
        ('draft', _('مسودة')),
        ('pending', _('قيد الانتظار')),
        ('approved', _('تمت الموافقة')),
        ('partial', _('استلام جزئي')),
        ('received', _('تم الاستلام')),
        ('cancelled', _('ملغي'))
    ]

    order_number = models.CharField(_('رقم الطلب'), max_length=50, unique=True)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='purchase_orders',
        verbose_name=_('المورد')
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        null=True,
        related_name='purchase_orders',
        verbose_name=_('المستودع')
    )
    status = models.CharField(_('الحالة'), max_length=10, choices=STATUS_CHOICES, default='draft')
    order_date = models.DateField(_('تاريخ الطلب'), auto_now_add=True)
    expected_date = models.DateField(_('تاريخ التسليم المتوقع'), null=True, blank=True)
    total_amount = models.DecimalField(_('إجمالي المبلغ'), max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(_('ملاحظات'), blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_purchase_orders',
        verbose_name=_('تم بواسطة')
    )

    class Meta:
        verbose_name = _('طلب شراء')
        verbose_name_plural = _('طلبات الشراء')
        ordering = ['-order_date']
        indexes = [
            models.Index(fields=['order_number'], name='po_number_idx'),
            models.Index(fields=['supplier'], name='po_supplier_idx'),
            models.Index(fields=['status'], name='po_status_idx'),
            models.Index(fields=['order_date'], name='po_date_idx'),
        ]

    def __str__(self):
        return f"{self.order_number} - {self.supplier.name}"

    def save(self, *args, **kwargs):
        # Generate order number if not provided
        if not self.order_number:
            year = datetime.now().year
            month = datetime.now().month
            self.order_number = f"PO-{year}{month:02d}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

class PurchaseOrderItem(models.Model):
    """
    Model for items in a purchase order
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('طلب الشراء')
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='purchase_order_items',
        verbose_name=_('المنتج')
    )
    quantity = models.PositiveIntegerField(_('الكمية'))
    unit_price = models.DecimalField(_('سعر الوحدة'), max_digits=10, decimal_places=2)
    received_quantity = models.PositiveIntegerField(_('الكمية المستلمة'), default=0)
    notes = models.TextField(_('ملاحظات'), blank=True)

    class Meta:
        verbose_name = _('عنصر طلب الشراء')
        verbose_name_plural = _('عناصر طلب الشراء')
        ordering = ['purchase_order', 'product']

    def __str__(self):
        return f"{self.purchase_order.order_number} - {self.product.name} ({self.quantity})"

    @property
    def subtotal(self):
        return self.quantity * self.unit_price

    @property
    def is_fully_received(self):
        return self.received_quantity >= self.quantity

class InventoryAdjustment(models.Model):
    """
    Model for inventory adjustments
    """
    ADJUSTMENT_TYPES = [
        ('increase', _('زيادة')),
        ('decrease', _('نقص')),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='adjustments',
        verbose_name=_('المنتج')
    )
    batch = models.ForeignKey(
        ProductBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adjustments',
        verbose_name=_('الدفعة')
    )
    adjustment_type = models.CharField(_('نوع التسوية'), max_length=10, choices=ADJUSTMENT_TYPES)
    quantity_before = models.DecimalField(_('الكمية قبل'), max_digits=10, decimal_places=2)
    quantity_after = models.DecimalField(_('الكمية بعد'), max_digits=10, decimal_places=2)
    reason = models.TextField(_('سبب التسوية'))
    date = models.DateTimeField(_('تاريخ التسوية'), auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='inventory_adjustments',
        verbose_name=_('تم بواسطة')
    )

    class Meta:
        verbose_name = _('تسوية مخزون')
        verbose_name_plural = _('تسويات المخزون')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['product'], name='adjustment_product_idx'),
            models.Index(fields=['adjustment_type'], name='adjustment_type_idx'),
            models.Index(fields=['date'], name='adjustment_date_idx'),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.get_adjustment_type_display()} ({self.quantity_before} -> {self.quantity_after})"

    @property
    def adjustment_quantity(self):
        return self.quantity_after - self.quantity_before

class StockAlert(models.Model):
    """
    Model for stock alerts
    """
    ALERT_TYPES = [
        ('low_stock', _('مخزون منخفض')),
        ('expiry', _('قرب انتهاء الصلاحية')),
        ('out_of_stock', _('نفاد المخزون')),
        ('overstock', _('فائض في المخزون')),
        ('price_change', _('تغير في السعر')),
    ]

    STATUS_CHOICES = [
        ('active', _('نشط')),
        ('resolved', _('تمت المعالجة')),
        ('ignored', _('تم تجاهله')),
    ]

    PRIORITY_CHOICES = [
        ('high', _('عالية')),
        ('medium', _('متوسطة')),
        ('low', _('منخفضة')),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='stock_alerts',
        verbose_name=_('المنتج')
    )
    alert_type = models.CharField(_('نوع التنبيه'), max_length=15, choices=ALERT_TYPES)
    message = models.TextField(_('رسالة التنبيه'))
    description = models.TextField(_('الوصف'), blank=True)
    priority = models.CharField(_('الأولوية'), max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(_('الحالة'), max_length=10, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    resolved_at = models.DateTimeField(_('تاريخ المعالجة'), null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_stock_alerts',
        verbose_name=_('تمت المعالجة بواسطة')
    )

    class Meta:
        verbose_name = _('تنبيه مخزون')
        verbose_name_plural = _('تنبيهات المخزون')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product'], name='alert_product_idx'),
            models.Index(fields=['alert_type'], name='alert_type_idx'),
            models.Index(fields=['status'], name='alert_status_idx'),
            models.Index(fields=['priority'], name='alert_priority_idx'),
            models.Index(fields=['created_at'], name='alert_created_at_idx'),
        ]

    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.product.name}"

    @classmethod
    def create_low_stock_alert(cls, product):
        """Create a low stock alert for a product"""
        if product.current_stock <= product.minimum_stock and product.current_stock > 0:
            # Check if there's already an active alert
            existing_alert = cls.objects.filter(
                product=product,
                alert_type='low_stock',
                status='active'
            ).first()

            if not existing_alert:
                return cls.objects.create(
                    product=product,
                    alert_type='low_stock',
                    message=f"المنتج {product.name} وصل للحد الأدنى للمخزون",
                    description=f"المخزون الحالي: {product.current_stock}, الحد الأدنى: {product.minimum_stock}",
                    priority='medium'
                )
            return existing_alert
        return None

    @classmethod
    def create_out_of_stock_alert(cls, product):
        """Create an out of stock alert for a product"""
        if product.current_stock <= 0:
            # Check if there's already an active alert
            existing_alert = cls.objects.filter(
                product=product,
                alert_type='out_of_stock',
                status='active'
            ).first()

            if not existing_alert:
                return cls.objects.create(
                    product=product,
                    alert_type='out_of_stock',
                    message=f"المنتج {product.name} نفذ من المخزون",
                    description=f"المخزون الحالي: {product.current_stock}, يرجى إعادة الطلب",
                    priority='high'
                )
            return existing_alert
        return None
