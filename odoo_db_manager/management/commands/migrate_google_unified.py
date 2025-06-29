"""
أمر Django لترحيل نظام Google إلى النظام الموحد
Django Command for migrating Google system to unified system
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from datetime import datetime
import logging

from odoo_db_manager.google_sync import GoogleSyncConfig, GoogleSyncLog
from odoo_db_manager.google_sync_advanced import GoogleSheetMapping, GoogleSyncTask

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'ترحيل نظام Google إلى النظام الموحد'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='تشغيل تجريبي دون حفظ التغييرات',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='فرض الترحيل حتى لو كانت البيانات موجودة',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS('🚀 بدء عملية ترحيل نظام Google الموحد')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️  تشغيل تجريبي - لن يتم حفظ التغييرات')
            )
        
        success_count = 0
        total_steps = 3
        
        try:
            with transaction.atomic():
                # 1. ترحيل الإعدادات
                if self.migrate_config_to_mapping(force):
                    success_count += 1
                
                # 2. ترحيل السجلات
                if self.migrate_logs_to_tasks(force):
                    success_count += 1
                
                # 3. تنظيف النظام القديم
                if self.cleanup_old_system():
                    success_count += 1
                
                if dry_run:
                    # إلغاء التغييرات في التشغيل التجريبي
                    transaction.set_rollback(True)
                    self.stdout.write(
                        self.style.WARNING('تم إلغاء التغييرات (تشغيل تجريبي)')
                    )
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'خطأ في الترحيل: {str(e)}')
            )
            return
        
        self.stdout.write('=' * 50)
        self.stdout.write(
            self.style.SUCCESS(f'📊 النتائج: {success_count}/{total_steps} خطوات نجحت')
        )
        
        if success_count == total_steps:
            self.stdout.write(
                self.style.SUCCESS('🎉 تمت عملية الترحيل بنجاح!')
            )
        else:
            self.stdout.write(
                self.style.WARNING('⚠️  بعض الخطوات فشلت')
            )

    def migrate_config_to_mapping(self, force=False):
        """ترحيل بيانات GoogleSyncConfig إلى GoogleSheetMapping"""
        
        self.stdout.write('🔄 بدء ترحيل إعدادات المزامنة...')
        
        try:
            # الحصول على الإعداد النشط
            old_config = GoogleSyncConfig.get_active_config()
            
            if not old_config:
                self.stdout.write(
                    self.style.WARNING('⚠️  لا يوجد إعداد مزامنة نشط للترحيل')
                )
                return True
            
            # التحقق من وجود تعيين مماثل
            existing_mapping = GoogleSheetMapping.objects.filter(
                spreadsheet_id=old_config.spreadsheet_id,
                name__icontains="مُرحَّل من النظام القديم"
            ).first()
            
            if existing_mapping and not force:
                self.stdout.write(
                    self.style.SUCCESS(f'✅ التعيين موجود بالفعل: {existing_mapping.name}')
                )
                return True
            
            # إنشاء تعيين جديد من الإعداد القديم
            mapping_data = {
                'name': f"تعيين مُرحَّل - {old_config.name}",
                'spreadsheet_id': old_config.spreadsheet_id,
                'sheet_name': "Sheet1",  # افتراضي
                'target_model': "customers.Customer",  # افتراضي
                'is_active': old_config.is_active,
                'last_sync': old_config.last_sync,
                'description': f"مُرحَّل من النظام القديم بتاريخ {datetime.now()}",
                
                # تعيين أعمدة افتراضي للعملاء
                'column_mappings': {
                    "A": "customer_name",
                    "B": "customer_phone", 
                    "C": "customer_email",
                    "D": "customer_address"
                },
                
                # إعدادات افتراضية
                'sync_options': {
                    "auto_create_records": True,
                    "update_existing": True,
                    "skip_empty_rows": True,
                    "validate_data": True
                }
            }
            
            if existing_mapping and force:
                # تحديث التعيين الموجود
                for key, value in mapping_data.items():
                    setattr(existing_mapping, key, value)
                existing_mapping.save()
                new_mapping = existing_mapping
                self.stdout.write(
                    self.style.SUCCESS(f'✅ تم تحديث التعيين: {new_mapping.name}')
                )
            else:
                # إنشاء تعيين جديد
                new_mapping = GoogleSheetMapping.objects.create(**mapping_data)
                self.stdout.write(
                    self.style.SUCCESS(f'✅ تم إنشاء التعيين الجديد: {new_mapping.name}')
                )
            
            # تعطيل الإعداد القديم
            old_config.is_active = False
            old_config.save()
            
            self.stdout.write(
                self.style.SUCCESS('✅ تم تعطيل الإعداد القديم')
            )
            return True
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في ترحيل الإعدادات: {str(e)}')
            )
            logger.error(f"Migration error: {str(e)}")
            return False

    def migrate_logs_to_tasks(self, force=False):
        """ترحيل سجلات المزامنة القديمة إلى مهام جديدة"""
        
        self.stdout.write('🔄 بدء ترحيل سجلات المزامنة...')
        
        try:
            # الحصول على السجلات القديمة
            old_logs = GoogleSyncLog.objects.all().order_by('-created_at')
            
            if not old_logs.exists():
                self.stdout.write(
                    self.style.WARNING('⚠️  لا توجد سجلات للترحيل')
                )
                return True
            
            # الحصول على التعيين المُرحَّل
            mapping = GoogleSheetMapping.objects.filter(
                name__icontains="مُرحَّل من النظام القديم"
            ).first()
            
            if not mapping:
                self.stdout.write(
                    self.style.ERROR('❌ لا يوجد تعيين مُرحَّل لربط السجلات به')
                )
                return False
            
            # الحصول على مستخدم النظام
            system_user = User.objects.filter(is_superuser=True).first()
            
            migrated_count = 0
            
            for old_log in old_logs:
                # التحقق من عدم وجود مهمة مُرحَّلة بالفعل
                existing_task = GoogleSyncTask.objects.filter(
                    mapping=mapping,
                    created_at=old_log.created_at
                ).first()
                
                if existing_task and not force:
                    continue
                
                # تحديد حالة المهمة بناءً على السجل
                status = 'completed'
                if 'فشل' in old_log.message or 'خطأ' in old_log.message:
                    status = 'failed'
                elif 'بدء' in old_log.message:
                    status = 'pending'
                
                task_data = {
                    'mapping': mapping,
                    'task_type': 'import',
                    'status': status,
                    'created_at': old_log.created_at,
                    'completed_at': old_log.created_at if status != 'pending' else None,
                    'created_by': system_user,
                    
                    # نقل البيانات المتاحة
                    'result_data': {
                        'migrated_from_old_log': True,
                        'old_log_id': old_log.id,
                        'message': old_log.message,
                        'operation_type': old_log.operation_type
                    }
                }
                
                if existing_task and force:
                    # تحديث المهمة الموجودة
                    for key, value in task_data.items():
                        setattr(existing_task, key, value)
                    existing_task.save()
                else:
                    # إنشاء مهمة جديدة
                    GoogleSyncTask.objects.create(**task_data)
                
                migrated_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ تم ترحيل {migrated_count} سجل إلى مهام جديدة')
            )
            return True
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في ترحيل السجلات: {str(e)}')
            )
            logger.error(f"Logs migration error: {str(e)}")
            return False

    def cleanup_old_system(self):
        """تنظيف النظام القديم (اختياري)"""
        
        self.stdout.write('🧹 تنظيف النظام القديم...')
        
        try:
            # يمكن حذف السجلات القديمة إذا رغبت
            # (محتفظ بها للأمان حالياً)
            
            self.stdout.write(
                self.style.SUCCESS('✅ تم الاحتفاظ بالبيانات القديمة للأمان')
            )
            self.stdout.write(
                self.style.WARNING('💡 يمكنك حذفها يدوياً لاحقاً إذا رغبت')
            )
            
            return True
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ خطأ في التنظيف: {str(e)}')
            )
            return False
