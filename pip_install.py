#!/usr/bin/env python3
"""
Pip wrapper script يقوم بتحديث requirements.txt تلقائياً عند تثبيت حزم جديدة
"""

import subprocess
import sys
import os
from pathlib import Path

def run_pip_install(*args):
    """تشغيل pip install وتحديث requirements.txt"""
    # تشغيل pip install
    cmd = [sys.executable, '-m', 'pip', 'install'] + list(args)
    print(f"تشغيل: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True)
        print("تم تثبيت الحزم بنجاح!")
        
        # تحديث requirements.txt
        update_requirements_auto()
        
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"خطأ في تثبيت الحزم: {e}")
        return e.returncode

def update_requirements_auto():
    """تحديث requirements.txt تلقائياً"""
    try:
        # البحث عن manage.py في المجلد الحالي أو المجلدات الأعلى
        current_dir = Path.cwd()
        manage_py_path = None
        
        for parent in [current_dir] + list(current_dir.parents):
            if (parent / 'manage.py').exists():
                manage_py_path = parent / 'manage.py'
                break
        
        if manage_py_path:
            print("تحديث ملف requirements.txt...")
            cmd = [sys.executable, str(manage_py_path), 'update_requirements', '--auto-add']
            subprocess.run(cmd, cwd=manage_py_path.parent, check=True)
            print("تم تحديث requirements.txt بنجاح!")
        else:
            print("لم يتم العثور على manage.py - يتم تشغيل السكريبت المستقل...")
            # تشغيل السكريبت المستقل
            script_path = current_dir / 'update_requirements.py'
            if script_path.exists():
                subprocess.run([sys.executable, str(script_path)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"تحذير: لم يتم تحديث requirements.txt: {e}")
    except Exception as e:
        print(f"تحذير: خطأ في تحديث requirements.txt: {e}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("الاستخدام: python pip_install.py <package_name> [package_name2] ...")
        print("مثال: python pip_install.py django requests")
        sys.exit(1)
    
    # إزالة اسم السكريبت من المعاملات
    packages = sys.argv[1:]
    
    # تشغيل pip install وتحديث requirements.txt
    exit_code = run_pip_install(*packages)
    sys.exit(exit_code)
