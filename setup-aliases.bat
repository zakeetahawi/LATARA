@echo off
REM إعداد alias لتثبيت الحزم وتحديث requirements.txt تلقائياً

echo تهيئة نظام إدارة الحزم التلقائي...

REM إنشاء alias لـ pip install
doskey pip-install=D:\crm\homeupdate\.venv\Scripts\python.exe D:\crm\homeupdate\pip_install.py $*

REM إنشاء alias لتحديث requirements.txt
doskey update-req=D:\crm\homeupdate\.venv\Scripts\python.exe D:\crm\homeupdate\manage.py update_requirements $*

REM إنشاء alias لتشغيل المشروع
doskey run-crm=D:\crm\homeupdate\.venv\Scripts\python.exe D:\crm\homeupdate\manage.py runserver

echo تم إعداد الأوامر التالية:
echo   pip-install [package_name] - تثبيت حزمة وتحديث requirements.txt
echo   update-req               - تحديث requirements.txt يدوياً
echo   run-crm                  - تشغيل الخادم
echo.
echo مثال: pip-install requests
echo مثال: update-req --auto-add
echo مثال: run-crm
