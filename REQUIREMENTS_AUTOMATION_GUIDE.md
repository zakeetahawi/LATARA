# نظام إدارة requirements.txt التلقائي - HomeUpdate CRM

## نظرة عامة

تم إعداد المشروع ليقوم بتحديث ملف `requirements.txt` تلقائياً عند تثبيت أي حزم جديدة. هذا يضمن أن جميع التبعيات محفوظة ومتتبعة بشكل صحيح.

## المكونات المثبتة

### 1. Django Management Command
**الملف:** `accounts/management/commands/update_requirements.py`

**الاستخدام:**
```bash
python manage.py update_requirements
python manage.py update_requirements --auto-add
```

### 2. Pip Wrapper Script
**الملف:** `pip_install.py`

**الاستخدام:**
```bash
python pip_install.py package_name
python pip_install.py django requests pandas
```

### 3. Git Pre-commit Hook
**الملف:** `.git/hooks/pre-commit`

يتم تشغيله تلقائياً قبل كل commit للتأكد من تحديث requirements.txt

### 4. Batch/PowerShell Aliases
**الملفات:** `setup-aliases.bat` و `setup-aliases.ps1`

## طرق الاستخدام

### الطريقة الأولى: استخدام Pip Wrapper (موصى به)
```bash
python pip_install.py requests
python pip_install.py django-extensions pandas numpy
```

### الطريقة الثانية: التثبيت العادي + التحديث اليدوي
```bash
pip install new_package
python manage.py update_requirements --auto-add
```

### الطريقة الثالثة: استخدام Aliases (بعد تشغيل setup)
```bash
# في Command Prompt
setup-aliases.bat
pip-install requests

# في PowerShell
.\setup-aliases.ps1
pip-install requests
```

## إعداد الـ Aliases

### في Command Prompt:
```bash
setup-aliases.bat
```

### في PowerShell:
```powershell
.\setup-aliases.ps1
```

بعد ذلك يمكنك استخدام:
- `pip-install package_name` - تثبيت وتحديث requirements.txt
- `update-req` - تحديث requirements.txt يدوياً  
- `run-crm` - تشغيل الخادم
- `django-shell` - فتح Django shell
- `django-migrate` - تشغيل migrations
- `django-makemigrations` - إنشاء migrations

## المميزات

✅ **تحديث تلقائي** لـ requirements.txt عند تثبيت حزم جديدة  
✅ **تجاهل الحزم الأساسية** (pip, setuptools, wheel)  
✅ **تطبيع أسماء الحزم** للتعامل مع اختلافات التسمية  
✅ **حفظ تاريخ الإضافة** في التعليقات  
✅ **دعم Git hooks** للتحديث التلقائي قبل commit  
✅ **سهولة الاستخدام** مع aliases مخصصة  

## أمثلة عملية

```bash
# تثبيت حزمة واحدة
python pip_install.py requests

# تثبيت عدة حزم
python pip_install.py celery redis django-cors-headers

# فحص وتحديث requirements.txt يدوياً
python manage.py update_requirements

# تحديث تلقائي بدون سؤال
python manage.py update_requirements --auto-add

# تشغيل الخادم
python manage.py runserver
```

## ملاحظات مهمة

1. **يتم إضافة الحزم الجديدة في نهاية** ملف requirements.txt
2. **يتم إضافة تعليق بتاريخ الإضافة** لكل مجموعة حزم
3. **النظام يتجاهل الحزم المحلية والأساسية** 
4. **Git pre-commit hook يعمل تلقائياً** عند كل commit
5. **يمكن تعطيل التحديث التلقائي** بحذف أو إعادة تسمية الـ hook

## حل المشاكل

### إذا لم يعمل pre-commit hook:
```bash
chmod +x .git/hooks/pre-commit
```

### إذا لم تعمل الـ aliases في PowerShell:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### للتحقق من الحزم المثبتة:
```bash
pip freeze
```

### لحفظ requirements.txt يدوياً:
```bash
pip freeze > requirements.txt
```

## الصيانة

- **مراجعة دورية** لملف requirements.txt لإزالة الحزم غير المستخدمة
- **تحديث الإصدارات** بانتظام للحصول على أحدث التحديثات الأمنية
- **اختبار البيئة** بعد أي تحديثات كبيرة

---

**تم إعداد النظام بنجاح! 🎉**

يمكنك الآن تثبيت أي حزمة وسيتم تحديث requirements.txt تلقائياً.
