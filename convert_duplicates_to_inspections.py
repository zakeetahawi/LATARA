from django.core.management.base import BaseCommand
from customers.models import Customer
from inspections.models import Inspection
from django.utils import timezone
from django.db import models

class Command(BaseCommand):
    help = 'تحويل العملاء المكررين (حسب رقم الهاتف) إلى طلبات معاينة مكتملة بتفاصيل افتراضية، مع حذف التكرارات. لا ينشئ معاينة للعملاء بدون رقم هاتف.'

    def handle(self, *args, **options):
        # البحث عن أرقام الهواتف المكررة (تجاهل الفراغ أو القيم الفارغة)
        duplicates = (
            Customer.objects.exclude(phone__isnull=True).exclude(phone__exact='')
            .values('phone')
            .annotate(count=models.Count('id'))
            .filter(count__gt=1)
        )
        total_created = 0
        for item in duplicates:
            phone = item['phone']
            customers = list(Customer.objects.filter(phone=phone))
            if len(customers) < 2:
                continue
            # احتفظ بعميل واحد فقط، والباقي حولهم إلى معاينات
            main_customer = customers[0]
            for duplicate in customers[1:]:
                # إنشاء طلب معاينة مكتمل
                Inspection.objects.create(
                    customer=main_customer,
                    branch=main_customer.branch,
                    status='completed',
                    result='passed',
                    request_date=timezone.now().date(),
                    scheduled_date=timezone.now().date(),
                    notes='تم التحويل تلقائياً من سجل مكرر',
                    created_by=main_customer.created_by
                )
                duplicate.delete()
                total_created += 1
        self.stdout.write(self.style.SUCCESS(f'تم تحويل {total_created} تكرار إلى طلبات معاينة مكتملة.'))
