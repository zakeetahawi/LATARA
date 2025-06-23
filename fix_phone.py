from django.core.management.base import BaseCommand
from customers.models import Customer
import re

class Command(BaseCommand):
    help = 'توحيد أرقام هواتف جميع العملاء حسب قواعد التنسيق المطلوبة.'

    def handle(self, *args, **options):
        updated = 0
        for customer in Customer.objects.all():
            old_phone = customer.phone or ''
            phone = old_phone.replace(' ', '')
            if '/' in phone:
                phone = phone.split('/')[0]
            if phone.startswith('20'):
                phone = '0' + phone[2:]
            elif phone.startswith('1'):
                phone = '0' + phone
            if phone != old_phone:
                customer.phone = phone
                customer.save()
                updated += 1
                self.stdout.write(self.style.SUCCESS(f'تم تحديث رقم العميل {customer.name}: {old_phone} → {phone}'))
        self.stdout.write(self.style.WARNING(f'تم تحديث {updated} رقم هاتف.'))
