"""
أمر Django لمزامنة Google Sheets
Django Command for Google Sheets Sync
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from odoo_db_manager.google_sync_advanced import GoogleSheetMapping, GoogleSyncTask
from odoo_db_manager.advanced_sync_service import AdvancedSyncService, SyncScheduler

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'مزامنة Google Sheets مع النظام'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mapping-id',
            type=int,
            help='معرف التعيين المحدد للمزامنة'
        )
        
        parser.add_argument(
            '--mapping-name',
            type=str,
            help='اسم التعيين للمزامنة'
        )
        
        parser.add_argument(
            '--all',
            action='store_true',
            help='مزامنة جميع التعيينات النشطة'
        )
        
        parser.add_argument(
            '--scheduled',
            action='store_true',
            help='تشغيل المزامنة المجدولة فقط'
        )
        
        parser.add_argument(
            '--reverse',
            action='store_true',
            help='تشغيل المزامنة العكسية (من النظام إلى Google Sheets)'
        )
        
        parser.add_argument(
            '--validate',
            action='store_true',
            help='التحقق من صحة التعيينات فقط'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='تشغيل تجريبي (عرض ما سيتم فعله دون تنفيذ)'
        )

    def handle(self, *args, **options):
        try:
            if options['validate']:
                self.validate_mappings()
            elif options['scheduled']:
                self.run_scheduled_syncs()
            elif options['all']:
                self.sync_all_mappings(options['reverse'], options['dry_run'])
            elif options['mapping_id']:
                self.sync_mapping_by_id(options['mapping_id'], options['reverse'], options['dry_run'])
            elif options['mapping_name']:
                self.sync_mapping_by_name(options['mapping_name'], options['reverse'], options['dry_run'])
            else:
                self.stdout.write(
                    self.style.ERROR('يجب تحديد أحد الخيارات: --mapping-id, --mapping-name, --all, --scheduled, أو --validate')
                )
                return

        except Exception as e:
            logger.error(f"خطأ في تنفيذ الأمر: {str(e)}")
            raise CommandError(f"خطأ في تنفيذ الأمر: {str(e)}")

    def validate_mappings(self):
        """التحقق من صحة جميع التعيينات"""
        self.stdout.write("جاري التحقق من صحة التعيينات...")
        
        mappings = GoogleSheetMapping.objects.filter(is_active=True)
        
        if not mappings.exists():
            self.stdout.write(self.style.WARNING("لا توجد تعيينات نشطة"))
            return
        
        valid_count = 0
        invalid_count = 0
        
        for mapping in mappings:
            try:
                errors = mapping.validate_mappings()
                if errors:
                    self.stdout.write(
                        self.style.ERROR(f"❌ {mapping.name}: {', '.join(errors)}")
                    )
                    invalid_count += 1
                else:
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ {mapping.name}: صحيح")
                    )
                    valid_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ {mapping.name}: خطأ في التحقق - {str(e)}")
                )
                invalid_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f"\nالنتيجة: {valid_count} صحيح، {invalid_count} غير صحيح")
        )

    def run_scheduled_syncs(self):
        """تشغيل المزامنة المجدولة"""
        self.stdout.write("جاري تشغيل المزامنة المجدولة...")
        
        try:
            SyncScheduler.run_scheduled_syncs()
            self.stdout.write(self.style.SUCCESS("تم تشغيل المزامنة المجدولة بنجاح"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"خطأ في المزامنة المجدولة: {str(e)}"))

    def sync_all_mappings(self, reverse=False, dry_run=False):
        """مزامنة جميع التعيينات النشطة"""
        sync_type = "العكسية" if reverse else "العادية"
        action = "عرض" if dry_run else "مزامنة"
        
        self.stdout.write(f"جاري {action} جميع التعيينات النشطة - المزامنة {sync_type}...")
        
        mappings = GoogleSheetMapping.objects.filter(is_active=True)
        
        if reverse:
            mappings = mappings.filter(enable_reverse_sync=True)
        
        if not mappings.exists():
            message = "لا توجد تعيينات نشطة مع المزامنة العكسية" if reverse else "لا توجد تعيينات نشطة"
            self.stdout.write(self.style.WARNING(message))
            return
        
        success_count = 0
        error_count = 0
        
        for mapping in mappings:
            try:
                if dry_run:
                    self.stdout.write(f"📋 سيتم مزامنة: {mapping.name} ({mapping.sheet_name})")
                    success_count += 1
                else:
                    result = self.sync_single_mapping(mapping, reverse)
                    if result['success']:
                        success_count += 1
                    else:
                        error_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ خطأ في {mapping.name}: {str(e)}")
                )
                error_count += 1
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"\nسيتم مزامنة {success_count} تعيين")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nالنتيجة: {success_count} نجح، {error_count} فشل")
            )

    def sync_mapping_by_id(self, mapping_id, reverse=False, dry_run=False):
        """مزامنة تعيين محدد بالمعرف"""
        try:
            mapping = GoogleSheetMapping.objects.get(id=mapping_id, is_active=True)
            
            if reverse and not mapping.enable_reverse_sync:
                self.stdout.write(
                    self.style.ERROR("المزامنة العكسية غير مفعلة لهذا التعيين")
                )
                return
            
            if dry_run:
                self.stdout.write(f"📋 سيتم مزامنة: {mapping.name} ({mapping.sheet_name})")
                return
            
            result = self.sync_single_mapping(mapping, reverse)
            
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(f"✅ تمت مزامنة {mapping.name} بنجاح")
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"❌ فشلت مزامنة {mapping.name}: {result.get('error')}")
                )
                
        except GoogleSheetMapping.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"التعيين {mapping_id} غير موجود أو غير نشط")
            )

    def sync_mapping_by_name(self, mapping_name, reverse=False, dry_run=False):
        """مزامنة تعيين محدد بالاسم"""
        try:
            mapping = GoogleSheetMapping.objects.get(name=mapping_name, is_active=True)
            
            if reverse and not mapping.enable_reverse_sync:
                self.stdout.write(
                    self.style.ERROR("المزامنة العكسية غير مفعلة لهذا التعيين")
                )
                return
            
            if dry_run:
                self.stdout.write(f"📋 سيتم مزامنة: {mapping.name} ({mapping.sheet_name})")
                return
            
            result = self.sync_single_mapping(mapping, reverse)
            
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(f"✅ تمت مزامنة {mapping.name} بنجاح")
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"❌ فشلت مزامنة {mapping.name}: {result.get('error')}")
                )
                
        except GoogleSheetMapping.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"التعيين '{mapping_name}' غير موجود أو غير نشط")
            )

    def sync_single_mapping(self, mapping, reverse=False):
        """مزامنة تعيين واحد"""
        sync_type = "العكسية" if reverse else "العادية"
        self.stdout.write(f"🔄 جاري مزامنة {mapping.name} - المزامنة {sync_type}...")
        
        # إنشاء مهمة
        task_type = 'reverse_sync' if reverse else 'import'
        task = GoogleSyncTask.objects.create(
            mapping=mapping,
            task_type=task_type
        )
        
        # تشغيل المزامنة
        sync_service = AdvancedSyncService(mapping)
        
        if reverse:
            result = sync_service.sync_to_sheets(task)
        else:
            result = sync_service.sync_from_sheets(task)
        
        # عرض النتائج
        if result['success']:
            if reverse:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ تمت المزامنة العكسية - تم تحديث {result.get('updated_rows', 0)} صف"
                    )
                )
            else:
                stats = result.get('stats', {})
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ تمت المزامنة - معالجة {stats.get('processed_rows', 0)} صف، "
                        f"نجح {stats.get('successful_rows', 0)}, فشل {stats.get('failed_rows', 0)}"
                    )
                )
                
                # عرض إحصائيات مفصلة
                if stats.get('created_customers', 0) > 0:
                    self.stdout.write(f"  📝 تم إنشاء {stats['created_customers']} عميل جديد")
                if stats.get('created_orders', 0) > 0:
                    self.stdout.write(f"  📦 تم إنشاء {stats['created_orders']} طلب جديد")
                if stats.get('created_inspections', 0) > 0:
                    self.stdout.write(f"  🔍 تم إنشاء {stats['created_inspections']} معاينة جديدة")
                if stats.get('created_installations', 0) > 0:
                    self.stdout.write(f"  🔧 تم إنشاء {stats['created_installations']} تركيب جديد")
                
                # عرض التعارضات
                conflicts = result.get('conflicts', 0)
                if conflicts > 0:
                    self.stdout.write(
                        self.style.WARNING(f"  ⚠️  {conflicts} تعارض يحتاج حل")
                    )
        else:
            self.stdout.write(
                self.style.ERROR(f"❌ فشلت المزامنة: {result.get('error')}")
            )
        
        return result
