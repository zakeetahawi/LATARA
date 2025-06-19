@echo off
title HomeUpdate CRM Server

echo ================================================
echo           HomeUpdate CRM System
echo ================================================
echo.

REM تشغيل التهيئة
call setup-aliases.bat

echo بدء تشغيل خادم Django...
echo.
echo الخادم سيعمل على: http://localhost:8000
echo لوقف الخادم اضغط Ctrl+C
echo.
echo ================================================

REM تشغيل خادم Django
D:\crm\homeupdate\.venv\Scripts\python.exe manage.py runserver

pause
