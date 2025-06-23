from django.core.management.base import BaseCommand
from customers.models import Customer
from django.db.models import Count, Q

class Command(BaseCommand):
    help = 'يعرض عدد العملاء المكررين بناءً على رقم الهاتف، أو بناءً على الاسم إذا لم يوجد رقم هاتف.'

    def handle(self, *args, **options):
        # التكرارات حسب رقم الهاتف (مع تجاهل القيم الفارغة)
        phone_duplicates = (
            Customer.objects.exclude(phone__isnull=True).exclude(phone__exact='')
            .values('phone')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )
        # التكرارات حسب الاسم فقط إذا لم يوجد رقم هاتف
        name_duplicates = (
            Customer.objects.filter(Q(phone__isnull=True) | Q(phone__exact=''))
            .values('name')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )
        total_duplicates = sum(item['count'] for item in phone_duplicates) + sum(item['count'] for item in name_duplicates)
        self.stdout.write(self.style.WARNING(f'عدد أرقام الهواتف المكررة: {len(phone_duplicates)}'))
        self.stdout.write(self.style.WARNING(f'عدد الأسماء المكررة بدون رقم هاتف: {len(name_duplicates)}'))
        self.stdout.write(self.style.WARNING(f'إجمالي العملاء المكررين (باحتساب كل تكرار): {total_duplicates}'))
        for item in phone_duplicates:
            self.stdout.write(f"الرقم: {item['phone']} - عدد العملاء: {item['count']}")
        for item in name_duplicates:
            self.stdout.write(f"الاسم (بدون رقم): {item['name']} - عدد العملاء: {item['count']}")
