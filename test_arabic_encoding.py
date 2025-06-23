#!/usr/bin/env python
"""
اختبار حل مشكلة الترميز العربي
Test Arabic encoding fix
"""

import os
import sys
import django

# إعداد Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
sys.path.append('d:/crm/homeupdate')
django.setup()

def test_arabic_filters():
    """اختبار فلاتر النصوص العربية"""
    try:
        from odoo_db_manager.templatetags.arabic_filters import (
            fix_arabic_encoding, clean_column_name, format_field_type, 
            is_arabic_text, debug_encoding
        )
        
        print("🧪 اختبار فلاتر النصوص العربية")
        print("=" * 50)
        
        # اختبار النصوص المختلفة
        test_cases = [
            "اسم العميل",
            "&#1575;&#1587;&#1605; &#1575;&#1604;&#1593;&#1605;&#1610;&#1604;",  # HTML entities
            "رقم الهاتف",
            "البريد الإلكتروني",
            "العنوان",
            "Name",
            "Phone Number",
            "customer_name",
            "",
            None,
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n🔍 اختبار {i}: {repr(test_case)}")
            
            try:
                # اختبار إصلاح الترميز
                fixed = fix_arabic_encoding(test_case)
                print(f"  ✅ إصلاح الترميز: {repr(fixed)}")
                
                # اختبار تنظيف اسم العمود
                cleaned = clean_column_name(test_case)
                print(f"  ✅ تنظيف العمود: {repr(cleaned)}")
                
                # اختبار تنسيق نوع الحقل
                formatted = format_field_type(test_case)
                print(f"  ✅ تنسيق النوع: {repr(formatted)}")
                
                # اختبار كشف النص العربي
                is_arabic = is_arabic_text(test_case)
                print(f"  ✅ نص عربي: {is_arabic}")
                
                # معلومات التشخيص
                debug_info = debug_encoding(test_case)
                print(f"  🔧 تشخيص: {debug_info}")
                
            except Exception as e:
                print(f"  ❌ خطأ: {str(e)}")
        
        return True
        
    except Exception as e:
        print(f"❌ خطأ في الاختبار: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_google_sheets_data():
    """اختبار جلب البيانات من Google Sheets"""
    try:
        from odoo_db_manager.google_sheets_import import GoogleSheetsImporter
        
        print("\n📊 اختبار جلب البيانات من Google Sheets")
        print("=" * 50)
        
        importer = GoogleSheetsImporter()
        importer.initialize()
        
        # جلب قائمة الصفحات
        sheets = importer.get_available_sheets()
        print(f"📋 الصفحات المتاحة: {sheets}")
        
        # اختبار جلب البيانات من صفحة عربية
        if "العملاء" in sheets:
            print(f"\n🔄 جلب البيانات من صفحة 'العملاء'...")
            data = importer.get_sheet_data("العملاء", import_all=False, start_row=1, end_row=5)
            
            if data:
                print(f"✅ تم جلب {len(data)} صف")
                print(f"📄 العناوين: {data[0]}")
                
                # اختبار الفلاتر على العناوين
                from odoo_db_manager.templatetags.arabic_filters import clean_column_name
                
                print("\n🧹 تنظيف العناوين:")
                for i, header in enumerate(data[0]):
                    cleaned = clean_column_name(header)
                    print(f"  {i+1}. '{header}' → '{cleaned}'")
            else:
                print("⚠️ لا توجد بيانات")
        else:
            print("❌ لم يتم العثور على صفحة 'العملاء'")
        
        return True
        
    except Exception as e:
        print(f"❌ خطأ في اختبار Google Sheets: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 بدء اختبار حل مشكلة الترميز العربي")
    print("=" * 60)
    
    # اختبار الفلاتر
    filters_success = test_arabic_filters()
    
    # اختبار Google Sheets
    sheets_success = test_google_sheets_data()
    
    print("\n" + "=" * 60)
    print("📊 نتائج الاختبار:")
    print(f"  🔧 فلاتر النصوص العربية: {'✅ نجح' if filters_success else '❌ فشل'}")
    print(f"  📊 Google Sheets: {'✅ نجح' if sheets_success else '❌ فشل'}")
    
    if filters_success and sheets_success:
        print("\n🎉 تم حل مشكلة الترميز العربي بنجاح!")
    else:
        print("\n💥 هناك مشاكل تحتاج إلى حل!")
