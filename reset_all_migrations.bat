@echo off
REM حذف جميع ملفات الترحيلات (ما عدا __init__.py) من كل التطبيقات المحلية

del /Q accounts\migrations\0*.py
if exist customers\migrations\0*.py del /Q customers\migrations\0*.py
if exist factory\migrations\0*.py del /Q factory\migrations\0*.py
if exist inspections\migrations\0*.py del /Q inspections\migrations\0*.py
if exist installations\migrations\0*.py del /Q installations\migrations\0*.py
if exist inventory\migrations\0*.py del /Q inventory\migrations\0*.py
if exist orders\migrations\0*.py del /Q orders\migrations\0*.py
if exist odoo_db_manager\migrations\0*.py del /Q odoo_db_manager\migrations\0*.py
if exist reports\migrations\0*.py del /Q reports\migrations\0*.py

REM حذف قاعدة البيانات crm_system وإعادة إنشائها
psql -U postgres -c "DROP DATABASE IF EXISTS crm_system;"
psql -U postgres -c "CREATE DATABASE crm_system;"

REM إنشاء الترحيلات من جديد
python manage.py makemigrations

REM تنفيذ الترحيلات
python manage.py migrate

echo تمت العملية بنجاح. اضغط أي زر للخروج.
pause
