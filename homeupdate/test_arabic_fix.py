#!/usr/bin/env python
"""
اختبار بسيط لحل مشكلة الأسماء العربية في Google Sheets
"""

import os
import sys
import django

# إعداد Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

def test_arabic_sheet_names():
    """اختبار جلب البيانات من صفحة بالاسم العربي"""
    try:
        from odoo_db_manager.google_sheets_import import GoogleSheetsImporter
        
        print("🔄 تهيئة المستورد...")
        importer = GoogleSheetsImporter()
        importer.initialize()
        print("✅ تم تهيئة المستورد بنجاح")
        
        print("\n🔄 جلب قائمة الصفحات...")
        sheets = importer.get_available_sheets()
        print(f"✅ تم جلب {len(sheets)} صفحة:")
        for i, sheet in enumerate(sheets, 1):
            print(f"  {i}. {sheet}")
        
        # اختبار جلب البيانات من صفحة عربية
        arabic_sheet_name = "العملاء"
        if arabic_sheet_name in sheets:
            print(f"\n🔄 جلب البيانات من صفحة '{arabic_sheet_name}'...")
            data = importer.get_sheet_data(arabic_sheet_name)
            print(f"✅ تم جلب {len(data)} صف من البيانات")
            
            if data:
                print(f"📋 العناوين: {data[0]}")
                if len(data) > 1:
                    print(f"📄 أول صف بيانات: {data[1]}")
            else:
                print("⚠️ لا توجد بيانات في الصفحة")
        else:
            print(f"❌ لم يتم العثور على صفحة '{arabic_sheet_name}'")
            print("الصفحات المتاحة:")
            for sheet in sheets:
                print(f"  - {sheet}")
        
        return True
        
    except Exception as e:
        print(f"❌ خطأ في الاختبار: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 بدء اختبار الأسماء العربية في Google Sheets")
    print("=" * 50)
    
    success = test_arabic_sheet_names()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 تم الاختبار بنجاح!")
    else:
        print("💥 فشل الاختبار!")
