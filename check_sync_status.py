"""
فحص حالة المزامنة والبيانات المنشأة
"""

import os
import sys
import django

# إعداد Django
sys.path.append('/d/crm/homeupdate')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'homeupdate.settings')
django.setup()

from odoo_db_manager.google_sync_advanced import GoogleSheetMapping, GoogleSyncTask
from customers.models import Customer
from orders.models import Order
from inspections.models import Inspection
from django.utils import timezone
from datetime import timedelta

def check_sync_status():
    """فحص حالة المزامنة والبيانات"""
    print("📊 تقرير حالة نظام المزامنة")
    print("="*50)
    
    # 1. فحص التعيينات
    mappings = GoogleSheetMapping.objects.all()
    active_mappings = mappings.filter(is_active=True)
    
    print(f"📋 التعيينات:")
    print(f"  إجمالي: {mappings.count()}")
    print(f"  نشط: {active_mappings.count()}")
    
    # 2. فحص المهام الأخيرة
    recent_tasks = GoogleSyncTask.objects.order_by('-created_at')[:10]
    print(f"\n📝 آخر المهام ({recent_tasks.count()}):")
    
    if recent_tasks:
        for task in recent_tasks:
            status_icon = {
                'completed': '✅',
                'failed': '❌', 
                'running': '🔄',
                'pending': '⏳'
            }.get(task.status, '❓')
            
            print(f"  {status_icon} مهمة #{task.id} - {task.mapping.name}")
            print(f"    الحالة: {task.status}")
            print(f"    التاريخ: {task.created_at.strftime('%Y-%m-%d %H:%M')}")
            print(f"    الصفوف المعالجة: {task.rows_processed}")
            print(f"    الصفوف الناجحة: {task.rows_successful}")
            print(f"    الصفوف الفاشلة: {task.rows_failed}")
            
            if task.error_log:
                print(f"    خطأ: {task.error_log[:100]}...")
            print()
    else:
        print("  لا توجد مهام مزامنة!")
        
    # 3. فحص البيانات المنشأة حديثاً
    last_24h = timezone.now() - timedelta(hours=24)
    
    recent_customers = Customer.objects.filter(created_at__gte=last_24h).count()
    recent_orders = Order.objects.filter(created_at__gte=last_24h).count()
    try:
        recent_inspections = Inspection.objects.filter(created_at__gte=last_24h).count()
    except:
        recent_inspections = 0
        
    print(f"📈 البيانات المنشأة في آخر 24 ساعة:")
    print(f"  عملاء: {recent_customers}")
    print(f"  طلبات: {recent_orders}")
    print(f"  معاينات: {recent_inspections}")
    
    # 4. إجمالي البيانات
    total_customers = Customer.objects.count()
    total_orders = Order.objects.count()
    try:
        total_inspections = Inspection.objects.count()
    except:
        total_inspections = 0
        
    print(f"\n📊 إجمالي البيانات في النظام:")
    print(f"  عملاء: {total_customers}")
    print(f"  طلبات: {total_orders}")
    print(f"  معاينات: {total_inspections}")
    
    # 5. فحص التعيينات المشكوك فيها
    print(f"\n🔍 فحص التكوين:")
    
    problematic_mappings = []
    for mapping in mappings:
        issues = []
        
        if not mapping.is_active:
            issues.append("غير نشط")
            
        if not mapping.get_column_mappings():
            issues.append("لا توجد تعيينات أعمدة")
            
        if not mapping.auto_create_customers:
            issues.append("إنشاء العملاء معطل")
            
        if not mapping.auto_create_orders:
            issues.append("إنشاء الطلبات معطل")
            
        if issues:
            problematic_mappings.append((mapping, issues))
            
    if problematic_mappings:
        print("  ⚠️ تعيينات تحتاج مراجعة:")
        for mapping, issues in problematic_mappings:
            print(f"    • {mapping.name}: {', '.join(issues)}")
    else:
        print("  ✅ جميع التعيينات تبدو سليمة")
        
    # 6. توصيات
    print(f"\n💡 التوصيات:")
    
    if not active_mappings.exists():
        print("  🔧 لا توجد تعيينات نشطة - قم بتفعيل تعيين أو إنشاء تعيين جديد")
    elif recent_tasks.count() == 0:
        print("  🔧 لم يتم تشغيل أي مزامنة - جرب تشغيل مزامنة تجريبية")
    elif recent_customers == 0 and recent_orders == 0:
        print("  🔧 لم يتم إنشاء بيانات جديدة - تحقق من:")
        print("    • تعيينات الأعمدة صحيحة")
        print("    • البيانات موجودة في Google Sheets")
        print("    • إعدادات الإنشاء التلقائي مفعلة")
    else:
        print("  ✅ النظام يعمل بشكل طبيعي")
        
    # 7. خطوات التشخيص التالية
    print(f"\n🔧 خطوات التشخيص المقترحة:")
    print("  1. تشغيل: python quick_diagnosis.py")
    print("  2. فحص تعيينات الأعمدة في واجهة الويب")
    print("  3. تشغيل مزامنة تجريبية ومراقبة النتائج")
    print("  4. فحص logs الخادم للأخطاء التفصيلية")

if __name__ == "__main__":
    check_sync_status()
