# إعداد aliases لـ PowerShell لإدارة الحزم تلقائياً

Write-Host "تهيئة نظام إدارة الحزم التلقائي..." -ForegroundColor Green

# إنشاء functions بدلاً من aliases في PowerShell
function pip-install {
    param([Parameter(ValueFromRemainingArguments)]$packages)
    & "D:\crm\homeupdate\.venv\Scripts\python.exe" "D:\crm\homeupdate\pip_install.py" @packages
}

function update-req {
    param([Parameter(ValueFromRemainingArguments)]$args)
    & "D:\crm\homeupdate\.venv\Scripts\python.exe" "D:\crm\homeupdate\manage.py" "update_requirements" @args
}

function run-crm {
    & "D:\crm\homeupdate\.venv\Scripts\python.exe" "D:\crm\homeupdate\manage.py" "runserver"
}

function django-shell {
    & "D:\crm\homeupdate\.venv\Scripts\python.exe" "D:\crm\homeupdate\manage.py" "shell"
}

function django-migrate {
    & "D:\crm\homeupdate\.venv\Scripts\python.exe" "D:\crm\homeupdate\manage.py" "migrate"
}

function django-makemigrations {
    & "D:\crm\homeupdate\.venv\Scripts\python.exe" "D:\crm\homeupdate\manage.py" "makemigrations"
}

Write-Host "تم إعداد الأوامر التالية:" -ForegroundColor Yellow
Write-Host "  pip-install [package_name] - تثبيت حزمة وتحديث requirements.txt" -ForegroundColor Cyan
Write-Host "  update-req               - تحديث requirements.txt يدوياً" -ForegroundColor Cyan
Write-Host "  run-crm                  - تشغيل الخادم" -ForegroundColor Cyan
Write-Host "  django-shell             - فتح Django shell" -ForegroundColor Cyan
Write-Host "  django-migrate           - تشغيل migrations" -ForegroundColor Cyan
Write-Host "  django-makemigrations    - إنشاء migrations" -ForegroundColor Cyan
Write-Host ""
Write-Host "أمثلة:" -ForegroundColor Green
Write-Host "  pip-install requests" -ForegroundColor White
Write-Host "  update-req --auto-add" -ForegroundColor White
Write-Host "  run-crm" -ForegroundColor White
