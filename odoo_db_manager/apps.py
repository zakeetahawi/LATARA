"""
تكوين تطبيق إدارة قواعد البيانات على طراز أودو
"""

import logging
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class OdooDbManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "odoo_db_manager"
    verbose_name = _("إدارة قواعد البيانات")

    def ready(self):
        """تهيئة التطبيق"""
        # استيراد الإشارات
        try:
            import odoo_db_manager.signals  # noqa: F401 (signals auto-register)
            from django.db import connection
            from django.db.utils import OperationalError
            
            try:
                # محاولة التحقق من وجود جدول Database
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM odoo_db_manager_database LIMIT 1")
                
                # إذا وصلنا هنا، فالجداول موجودة ويمكننا المزامنة
                from .services.database_service import DatabaseService
                database_service = DatabaseService()
                database_service.sync_databases_from_settings()
                database_service.sync_discovered_databases()
                
            except OperationalError:
                # الجداول غير موجودة بعد، تخطي المزامنة
                logger.info("Skipping database sync - tables not created yet")

            # بدء تشغيل خدمة النسخ الاحتياطية المجدولة
            import os
            if os.environ.get('RUN_MAIN', None) != 'true':
                # تجنب التشغيل المزدوج في وضع التطوير
                try:
                    from .services.scheduled_backup_service import scheduled_backup_service
                    scheduled_backup_service.start()
                    logger.info("Scheduled backup service started successfully")
                except Exception as scheduler_error:
                    logger.warning(f"Failed to start scheduler: {str(scheduler_error)}")
                    logger.info("Manual backups will be used in production")
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Error during app initialization: {str(e)}")
