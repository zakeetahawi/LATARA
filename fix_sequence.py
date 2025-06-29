#!/usr/bin/env python
import os
import django

# إعداد Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from django.db import connection

def fix_sequence():
    """إصلاح sequence لجدول google_sync_task"""
    with connection.cursor() as cursor:
        # البحث عن اسم sequence الصحيح
        cursor.execute("""
            SELECT pg_get_serial_sequence('google_sync_task', 'id');
        """)
        sequence_name = cursor.fetchone()[0]
        
        if sequence_name:
            # الحصول على أعلى ID موجود
            cursor.execute("SELECT COALESCE(MAX(id), 0) FROM google_sync_task;")
            max_id = cursor.fetchone()[0]
            
            # إعادة تعيين sequence
            next_id = max_id + 1
            cursor.execute(f"SELECT setval('{sequence_name}', {next_id}, false);")
            
            print(f"Fixed sequence: {sequence_name}, max ID: {max_id}, next: {next_id}")
        else:
            print("No sequence found")
            
            # مسح البيانات الموجودة في الجدول إذا كان sequence غير موجود
            cursor.execute("DELETE FROM google_sync_task;")
            print("Deleted all data from table")

if __name__ == '__main__':
    fix_sequence()
