#!/usr/bin/env python3
"""
نظام تحديث ملف requirements.txt تلقائياً
يقوم بمقارنة الحزم المثبتة مع الموجودة في requirements.txt ويضيف الناقصة
"""

import subprocess
import sys
import re
import os
from pathlib import Path

def get_installed_packages():
    """الحصول على قائمة بالحزم المثبتة"""
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], 
                              capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n')
    except subprocess.CalledProcessError as e:
        print(f"خطأ في الحصول على قائمة الحزم المثبتة: {e}")
        return []

def parse_requirements_file(requirements_path):
    """قراءة وتحليل ملف requirements.txt"""
    if not os.path.exists(requirements_path):
        return set(), []
    
    with open(requirements_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    packages = set()
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('-'):
            # استخراج اسم الحزمة (قبل == أو >= أو <= إلخ)
            package_name = re.split(r'[><=!]', line)[0].strip()
            packages.add(package_name.lower())
    
    return packages, lines

def normalize_package_name(name):
    """تطبيع أسماء الحزم (تحويل _ إلى -)"""
    return name.replace('_', '-').lower()

def update_requirements():
    """تحديث ملف requirements.txt بالحزم الجديدة"""
    base_dir = Path(__file__).parent
    requirements_path = base_dir / 'requirements.txt'
    
    print("جاري تحديث ملف requirements.txt...")
    
    # الحصول على الحزم المثبتة
    installed_packages = get_installed_packages()
    if not installed_packages:
        print("لم يتم العثور على حزم مثبتة")
        return
    
    # قراءة ملف requirements.txt الحالي
    existing_packages, lines = parse_requirements_file(requirements_path)
    
    # تحليل الحزم المثبتة
    new_packages = []
    for package_line in installed_packages:
        if '==' in package_line:
            package_name = package_line.split('==')[0].strip()
            normalized_name = normalize_package_name(package_name)
            
            # تجاهل الحزم الأساسية والمحلية
            if normalized_name in ['pip', 'setuptools', 'wheel']:
                continue
            
            # التحقق من عدم وجود الحزمة في requirements.txt
            if normalized_name not in existing_packages:
                new_packages.append(package_line)
    
    if new_packages:
        print(f"تم العثور على {len(new_packages)} حزمة جديدة:")
        for package in new_packages:
            print(f"  - {package}")
        
        # إضافة الحزم الجديدة إلى نهاية الملف
        with open(requirements_path, 'a', encoding='utf-8') as f:
            f.write(f"\n# حزم مضافة تلقائياً في {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            for package in new_packages:
                f.write(f"{package}\n")
        
        print(f"تم إضافة الحزم الجديدة إلى {requirements_path}")
    else:
        print("لا توجد حزم جديدة للإضافة")

if __name__ == '__main__':
    update_requirements()
