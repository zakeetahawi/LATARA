#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script لإنشاء نسخة احتياطية بترميز UTF-8 صحيح
"""
import os
import sys
import django
from django.conf import settings

# إضافة مسار المشروع
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# تعيين متغير البيئة للإعدادات
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')

# تهيئة Django
django.setup()

def create_backup():
    """إنشاء نسخة احتياطية آمنة"""
    from django.core.management import call_command
    from io import StringIO
    import json
    
    try:
        print("🔄 بدء إنشاء النسخة الاحتياطية...")
        
        # تحديد التطبيقات
        apps_to_backup = ['accounts', 'customers']
        
        # إنشاء buffer
        output = StringIO()
        
        # تنفيذ dumpdata
        call_command('dumpdata', *apps_to_backup, stdout=output, format='json', indent=2)
        
        # حفظ البيانات
        backup_file = 'backup_safe.json'
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(output.getvalue())
        
        # التحقق من النتيجة
        file_size = os.path.getsize(backup_file)
        print(f"✅ تم إنشاء النسخة الاحتياطية بنجاح!")
        print(f"📁 الملف: {backup_file}")
        print(f"📊 الحجم: {file_size} بايت")
        
        # قراءة وعرض عينة من البيانات
        with open(backup_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"📋 عدد العناصر: {len(data)}")
            if data:
                print(f"🔍 أول عنصر: {data[0].get('model', 'غير معروف')}")
        
        return True
        
    except Exception as e:
        print(f"❌ خطأ في إنشاء النسخة الاحتياطية: {str(e)}")
        return False

if __name__ == '__main__':
    create_backup()
