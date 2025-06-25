from django.db.models.signals import post_save
from django.dispatch import receiver
from accounts.models import SystemSettings
from .models import Product, StockTransaction

@receiver(post_save, sender=SystemSettings)
def update_currency_on_settings_change(sender, instance, **kwargs):
    """تحديث العملة لجميع المنتجات عند تغيير إعدادات النظام"""
    # استخدم الحقل الصحيح (currency) بدلاً من default_currency
    if hasattr(instance, 'currency') and instance.currency:
        Product.objects.all().update(currency=instance.currency)

@receiver(post_save, sender=StockTransaction)
def update_running_balance(sender, instance, created, **kwargs):
    """تحديث الرصيد المتحرك للمعاملات"""
    if created:
        # حساب الرصيد المتحرك
        previous_balance = StockTransaction.objects.filter(
            product=instance.product,
            transaction_date__lt=instance.transaction_date
        ).exclude(id=instance.id).order_by('-transaction_date').first()

        current_balance = previous_balance.running_balance if previous_balance else 0

        if instance.transaction_type == 'in':
            instance.running_balance = current_balance + instance.quantity
        else:
            instance.running_balance = current_balance - instance.quantity

        # تجنب التكرار عند الحفظ
        StockTransaction.objects.filter(id=instance.id).update(running_balance=instance.running_balance)

        # تحديث الأرصدة اللاحقة
        subsequent_transactions = StockTransaction.objects.filter(
            product=instance.product,
            transaction_date__gt=instance.transaction_date
        ).exclude(id=instance.id).order_by('transaction_date')

        current_balance = instance.running_balance
        for trans in subsequent_transactions:
            if trans.transaction_type == 'in':
                current_balance += trans.quantity
            else:
                current_balance -= trans.quantity
            StockTransaction.objects.filter(id=trans.id).update(running_balance=current_balance)