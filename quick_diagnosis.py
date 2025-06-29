"""
أداة تشخيص سريعة لمشاكل المزامنة
Quick diagnosis tool for sync issues
"""

import os
import sys
import django

# إعداد Django
sys.path.append('/d/crm/homeupdate')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'homeupdate.settings')
django.setup()

from odoo_db_manager.google_sync_advanced import GoogleSheetMapping
from odoo_db_manager.advanced_sync_service import AdvancedSyncService
from odoo_db_manager.google_sheets_import import GoogleSheetsImporter

def diagnose_all_mappings():
    """تشخيص جميع التعيينات"""
    print("🔍 تشخيص نظام المزامنة المتقدمة\n")
    
    # 1. فحص التعيينات الموجودة
    mappings = GoogleSheetMapping.objects.all()
    print(f"📋 عدد التعيينات الموجودة: {mappings.count()}")
    
    if not mappings.exists():
        print("❌ لا توجد تعيينات! يجب إنشاء تعيين أولاً.")
        return
    
    for mapping in mappings:
        print(f"\n{'='*50}")
        print(f"🔍 التعيين: {mapping.name} (ID: {mapping.id})")
        print(f"{'='*50}")
        
        # فحص الحالة الأساسية
        print(f"نشط: {'✅ نعم' if mapping.is_active else '❌ لا'}")
        print(f"معرف الجدول: {mapping.spreadsheet_id[:20]}...")
        print(f"اسم الصفحة: {mapping.sheet_name}")
        print(f"صف العناوين: {mapping.header_row}")
        print(f"صف البداية: {mapping.start_row}")
        
        # فحص تعيينات الأعمدة
        column_mappings = mapping.get_column_mappings()
        print(f"\n📋 تعيينات الأعمدة ({len(column_mappings)}):")
        
        if not column_mappings:
            print("❌ لا توجد تعيينات أعمدة! هذا هو السبب الرئيسي!")
            print("💡 الحل: اذهب إلى صفحة تفاصيل التعيين → تحديث التعيينات")
            continue
            
        # عرض التعيينات
        customer_fields = []
        order_fields = []
        
        for col, field in column_mappings.items():
            if field in ['customer_name', 'customer_phone', 'customer_code', 'customer_email', 'customer_address']:
                customer_fields.append(f"{col} → {field}")
            elif field in ['order_number', 'invoice_number', 'contract_number', 'order_date', 'total_amount']:
                order_fields.append(f"{col} → {field}")
            
        print("  🧑‍💼 حقول العميل:")
        if customer_fields:
            for field in customer_fields:
                print(f"    ✅ {field}")
        else:
            print("    ❌ لا توجد حقول عميل معيّنة!")
            
        print("  📦 حقول الطلب:")
        if order_fields:
            for field in order_fields:
                print(f"    ✅ {field}")
        else:
            print("    ❌ لا توجد حقول طلب معيّنة!")
        
        # فحص الإعدادات
        print(f"\n⚙️ إعدادات الإنشاء التلقائي:")
        print(f"  إنشاء عملاء: {'✅' if mapping.auto_create_customers else '❌'}")
        print(f"  إنشاء طلبات: {'✅' if mapping.auto_create_orders else '❌'}")
        print(f"  إنشاء معاينات: {'✅' if mapping.auto_create_inspections else '❌'}")
        print(f"  تحديث الموجود: {'✅' if mapping.update_existing else '❌'}")
        
        # فحص صحة التعيينات
        errors = mapping.validate_mappings()
        if errors:
            print(f"\n❌ أخطاء في التعيين:")
            for error in errors:
                print(f"  • {error}")
        else:
            print(f"\n✅ التعيين صحيح نظرياً")
            
        # فحص الاتصال بـ Google Sheets
        print(f"\n🔗 فحص جلب البيانات من Google Sheets:")
        try:
            importer = GoogleSheetsImporter()
            importer.initialize()
            
            # تحديث معرف الجدول مؤقتاً
            original_id = getattr(importer.config, 'spreadsheet_id', None)
            
            if hasattr(importer.config, 'spreadsheet_id'):
                importer.config.spreadsheet_id = mapping.spreadsheet_id
            
            try:
                sheet_data = importer.get_sheet_data(mapping.sheet_name)
                if sheet_data and len(sheet_data) >= mapping.start_row:
                    data_rows = sheet_data[mapping.start_row - 1:]
                    print(f"  ✅ تم جلب {len(data_rows)} صف من البيانات")
                    
                    # عرض عينة من أول صف
                    if data_rows and len(sheet_data) >= mapping.header_row:
                        headers = sheet_data[mapping.header_row - 1]
                        first_row = data_rows[0]
                        
                        print(f"  📋 عينة من البيانات:")
                        for i, (header, value) in enumerate(zip(headers[:5], first_row[:5])):
                            mapped_field = column_mappings.get(header, 'غير معيّن')
                            print(f"    {header}: '{value}' → {mapped_field}")
                            
                else:
                    print(f"  ❌ لا توجد بيانات كافية في الجدول")
                    
            finally:
                # استعادة المعرف الأصلي
                if original_id and hasattr(importer.config, 'spreadsheet_id'):
                    importer.config.spreadsheet_id = original_id
                    
        except Exception as e:
            print(f"  ❌ خطأ في جلب البيانات: {str(e)}")
            
        # الخلاصة والتوصيات
        print(f"\n💡 التوصيات:")
        if not column_mappings:
            print("  🔧 أولوية عالية: أضف تعيينات الأعمدة!")
        elif not customer_fields:
            print("  🔧 أضف تعيينات لحقول العميل (اسم، هاتف)")
        elif not order_fields:
            print("  🔧 أضف تعيينات لحقول الطلب (رقم فاتورة، رقم طلب)")
        elif not mapping.auto_create_orders:
            print("  🔧 فعّل 'إنشاء طلبات تلقائياً'")
        elif not mapping.auto_create_customers:
            print("  🔧 فعّل 'إنشاء عملاء تلقائياً'")
        else:
            print("  ✅ التكوين يبدو صحيحاً - جرب تشغيل المزامنة ومراقبة النتائج")

if __name__ == "__main__":
    diagnose_all_mappings()
