# إعداد المشروع التلقائي لـ HomeUpdate CRM

هذا المجلد يحتوي على نظام تلقائي لإدارة ملف requirements.txt

## الأدوات المتوفرة:

### 1. Django Management Command
```bash
python manage.py update_requirements
python manage.py update_requirements --auto-add
```

### 2. Pip Wrapper Script
بدلاً من استخدام `pip install` مباشرة، استخدم:
```bash
python pip_install.py package_name
python pip_install.py django requests pandas
```

### 3. السكريبت المستقل
```bash
python update_requirements.py
```

### 4. Git Pre-commit Hook
يتم تشغيله تلقائياً قبل كل commit للتأكد من تحديث requirements.txt

## كيفية الاستخدام:

### لتثبيت حزمة جديدة وتحديث requirements.txt تلقائياً:
```bash
python pip_install.py new_package_name
```

### لفحص وتحديث requirements.txt يدوياً:
```bash
python manage.py update_requirements
```

### لتحديث requirements.txt بدون سؤال:
```bash
python manage.py update_requirements --auto-add
```

## المميزات:
- تحديث تلقائي لـ requirements.txt عند تثبيت حزم جديدة
- تجاهل الحزم الأساسية (pip, setuptools, wheel)
- تطبيع أسماء الحزم للتعامل مع الاختلافات في التسمية
- حفظ تاريخ الإضافة في التعليقات
- دعم Git hooks للتحديث التلقائي

## ملاحظات:
- يتم إضافة الحزم الجديدة في نهاية ملف requirements.txt
- يتم إضافة تعليق بتاريخ الإضافة
- النظام يتجاهل الحزم المحلية والأساسية
