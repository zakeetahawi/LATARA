import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from odoo_db_manager.google_sync_advanced import GoogleSheetMapping, GoogleSyncTask, AdvancedSyncService
from accounts.models import User

# جلب التعيين والمستخدم
mapping = GoogleSheetMapping.objects.get(name="test")
user = User.objects.first()

print(f'التعيين: {mapping.name}')
print(f'معرف الجدول: {mapping.spreadsheet_id}')
print(f'اسم الصفحة: {mapping.sheet_name}')
print(f'تعيينات الأعمدة: {mapping.column_mappings}')

# إنشاء مهمة جديدة
task = GoogleSyncTask.objects.create(
    mapping=mapping,
    task_type='import',
    created_by=user
)

print(f'\nتم إنشاء المهمة: {task.id}')

# تشغيل المهمة
task.start_task()

# تنفيذ المزامنة
service = AdvancedSyncService(mapping)
result = service.sync_from_sheets(task)

print('\nنتيجة المزامنة:')
print(f'نجحت: {result["success"]}')

if result['success']:
    task.mark_completed(result)
    stats = result['stats']
    print('الإحصائيات:')
    print(f'  - إجمالي الصفوف: {stats["total_rows"]}')
    print(f'  - الصفوف المعالجة: {stats["processed_rows"]}')
    print(f'  - العملاء الجدد: {stats["customers_created"]}')
    print(f'  - العملاء المحدثون: {stats["customers_updated"]}')
    print(f'  - الطلبات الجديدة: {stats["orders_created"]}')
    print(f'  - الطلبات المحدثة: {stats["orders_updated"]}')
    print(f'  - الأخطاء: {len(stats["errors"])}')
    if stats['errors']:
        print(f'  - أول خطأ: {stats["errors"][0]}')
else:
    task.mark_failed(result.get('error', 'خطأ غير معروف'))
    print(f'خطأ: {result.get("error")}')
