"""
Django management command لتحديث ملف requirements.txt تلقائياً
"""

from django.core.management.base import BaseCommand
import subprocess
import sys
import re
import os
from pathlib import Path
from django.conf import settings

class Command(BaseCommand):
    help = 'تحديث ملف requirements.txt بالحزم المثبتة حديثاً'

    def add_arguments(self, parser):
        parser.add_argument(
            '--auto-add',
            action='store_true',
            help='إضافة الحزم الجديدة تلقائياً بدون سؤال',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('بدء تحديث ملف requirements.txt...'))
        
        base_dir = Path(settings.BASE_DIR)
        requirements_path = base_dir / 'requirements.txt'
        
        # الحصول على الحزم المثبتة
        installed_packages = self.get_installed_packages()
        if not installed_packages:
            self.stdout.write(self.style.ERROR('لم يتم العثور على حزم مثبتة'))
            return
        
        # قراءة ملف requirements.txt الحالي
        existing_packages, lines = self.parse_requirements_file(requirements_path)
        
        # العثور على الحزم الجديدة
        new_packages = self.find_new_packages(installed_packages, existing_packages)
        
        if not new_packages:
            self.stdout.write(self.style.SUCCESS('جميع الحزم موجودة في requirements.txt'))
            return
        
        self.stdout.write(f'تم العثور على {len(new_packages)} حزمة جديدة:')
        for package in new_packages:
            self.stdout.write(f'  - {package}')
        
        # السؤال عن الإضافة إذا لم يتم تحديد --auto-add
        if not options['auto_add']:
            response = input('\nهل تريد إضافة هذه الحزم إلى requirements.txt؟ (y/n): ')
            if response.lower() not in ['y', 'yes', 'نعم']:
                self.stdout.write('تم إلغاء العملية')
                return
        
        # إضافة الحزم الجديدة
        self.add_packages_to_requirements(requirements_path, new_packages)
        self.stdout.write(self.style.SUCCESS(f'تم إضافة {len(new_packages)} حزمة إلى requirements.txt'))

    def get_installed_packages(self):
        """الحصول على قائمة بالحزم المثبتة"""
        try:
            result = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], 
                                  capture_output=True, text=True, check=True)
            return result.stdout.strip().split('\n')
        except subprocess.CalledProcessError as e:
            self.stdout.write(self.style.ERROR(f'خطأ في الحصول على قائمة الحزم المثبتة: {e}'))
            return []

    def parse_requirements_file(self, requirements_path):
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
                packages.add(self.normalize_package_name(package_name))
        
        return packages, lines

    def normalize_package_name(self, name):
        """تطبيع أسماء الحزم (تحويل _ إلى -)"""
        return name.replace('_', '-').lower()

    def find_new_packages(self, installed_packages, existing_packages):
        """البحث عن الحزم الجديدة غير الموجودة في requirements.txt"""
        new_packages = []
        
        for package_line in installed_packages:
            if '==' in package_line:
                package_name = package_line.split('==')[0].strip()
                normalized_name = self.normalize_package_name(package_name)
                
                # تجاهل الحزم الأساسية والمحلية
                if normalized_name in ['pip', 'setuptools', 'wheel']:
                    continue
                
                # التحقق من عدم وجود الحزمة في requirements.txt
                if normalized_name not in existing_packages:
                    new_packages.append(package_line)
        
        return new_packages

    def add_packages_to_requirements(self, requirements_path, new_packages):
        """إضافة الحزم الجديدة إلى ملف requirements.txt"""
        with open(requirements_path, 'a', encoding='utf-8') as f:
            f.write(f"\n# حزم مضافة تلقائياً في {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            for package in new_packages:
                f.write(f"{package}\n")
