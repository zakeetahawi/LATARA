"""
مهام Celery للمزامنة المتقدمة مع Google Sheets
Celery Tasks for Advanced Google Sheets Sync
"""

import logging
from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from .google_sync_advanced import GoogleSheetMapping, GoogleSyncTask, GoogleSyncSchedule
from .advanced_sync_service import AdvancedSyncService, SyncScheduler

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_google_sheet_task(self, mapping_id, task_id=None, user_id=None):
    """
    مهمة مزامنة Google Sheet
    """
    try:
        # جلب التعيين
        mapping = GoogleSheetMapping.objects.get(id=mapping_id)
        
        # جلب أو إنشاء المهمة
        if task_id:
            task = GoogleSyncTask.objects.get(id=task_id)
        else:
            task = GoogleSyncTask.objects.create(
                mapping=mapping,
                task_type='import',
                created_by_id=user_id
            )
        
        # تشغيل المزامنة
        sync_service = AdvancedSyncService(mapping)
        result = sync_service.sync_from_sheets(task)
        
        # إرسال إشعار بالنتيجة
        if result['success']:
            logger.info(f"تمت مزامنة {mapping.name} بنجاح")
            
            # إرسال بريد إلكتروني للمستخدم
            if user_id and hasattr(settings, 'EMAIL_HOST'):
                send_sync_notification(user_id, mapping, task, success=True)
        else:
            logger.error(f"فشلت مزامنة {mapping.name}: {result.get('error')}")
            
            # إرسال بريد إلكتروني بالخطأ
            if user_id and hasattr(settings, 'EMAIL_HOST'):
                send_sync_notification(user_id, mapping, task, success=False, error=result.get('error'))
        
        return result
        
    except GoogleSheetMapping.DoesNotExist:
        logger.error(f"التعيين {mapping_id} غير موجود")
        return {'success': False, 'error': 'التعيين غير موجود'}
    
    except Exception as e:
        logger.error(f"خطأ في مهمة المزامنة: {str(e)}")
        
        # إعادة المحاولة
        if self.request.retries < self.max_retries:
            logger.info(f"إعادة محاولة المزامنة {mapping_id} - المحاولة {self.request.retries + 1}")
            raise self.retry(countdown=60 * (self.request.retries + 1))
        
        # فشل نهائي
        if task_id:
            try:
                task = GoogleSyncTask.objects.get(id=task_id)
                task.fail_task(str(e))
            except:
                pass
        
        return {'success': False, 'error': str(e)}


@shared_task
def reverse_sync_task(mapping_id, user_id=None):
    """
    مهمة المزامنة العكسية (من النظام إلى Google Sheets)
    """
    try:
        # جلب التعيين
        mapping = GoogleSheetMapping.objects.get(id=mapping_id)
        
        if not mapping.enable_reverse_sync:
            return {'success': False, 'error': 'المزامنة العكسية غير مفعلة'}
        
        # إنشاء مهمة
        task = GoogleSyncTask.objects.create(
            mapping=mapping,
            task_type='reverse_sync',
            created_by_id=user_id
        )
        
        # تشغيل المزامنة العكسية
        sync_service = AdvancedSyncService(mapping)
        result = sync_service.sync_to_sheets(task)
        
        logger.info(f"تمت المزامنة العكسية لـ {mapping.name}")
        return result
        
    except GoogleSheetMapping.DoesNotExist:
        logger.error(f"التعيين {mapping_id} غير موجود")
        return {'success': False, 'error': 'التعيين غير موجود'}
    
    except Exception as e:
        logger.error(f"خطأ في المزامنة العكسية: {str(e)}")
        return {'success': False, 'error': str(e)}


@shared_task
def run_scheduled_syncs():
    """
    تشغيل المزامنة المجدولة
    """
    try:
        logger.info("بدء تشغيل المزامنة المجدولة")
        
        # تشغيل المجدول
        SyncScheduler.run_scheduled_syncs()
        
        logger.info("انتهاء تشغيل المزامنة المجدولة")
        return {'success': True}
        
    except Exception as e:
        logger.error(f"خطأ في تشغيل المزامنة المجدولة: {str(e)}")
        return {'success': False, 'error': str(e)}


@shared_task
def cleanup_old_tasks():
    """
    تنظيف المهام القديمة
    """
    try:
        # حذف المهام المكتملة الأقدم من 30 يوم
        cutoff_date = timezone.now() - timezone.timedelta(days=30)
        
        old_tasks = GoogleSyncTask.objects.filter(
            status__in=['completed', 'failed'],
            completed_at__lt=cutoff_date
        )
        
        count = old_tasks.count()
        old_tasks.delete()
        
        logger.info(f"تم حذف {count} مهمة قديمة")
        return {'success': True, 'deleted_count': count}
        
    except Exception as e:
        logger.error(f"خطأ في تنظيف المهام القديمة: {str(e)}")
        return {'success': False, 'error': str(e)}


@shared_task
def sync_all_active_mappings():
    """
    مزامنة جميع التعيينات النشطة
    """
    try:
        active_mappings = GoogleSheetMapping.objects.filter(is_active=True)
        results = []
        
        for mapping in active_mappings:
            try:
                # تشغيل مزامنة غير متزامنة
                task_result = sync_google_sheet_task.delay(mapping.id)
                results.append({
                    'mapping_id': mapping.id,
                    'mapping_name': mapping.name,
                    'task_id': task_result.id,
                    'status': 'started'
                })
            except Exception as e:
                logger.error(f"خطأ في بدء مزامنة {mapping.name}: {str(e)}")
                results.append({
                    'mapping_id': mapping.id,
                    'mapping_name': mapping.name,
                    'status': 'failed',
                    'error': str(e)
                })
        
        return {
            'success': True,
            'total_mappings': len(active_mappings),
            'results': results
        }
        
    except Exception as e:
        logger.error(f"خطأ في مزامنة جميع التعيينات: {str(e)}")
        return {'success': False, 'error': str(e)}


@shared_task
def validate_all_mappings():
    """
    التحقق من صحة جميع التعيينات
    """
    try:
        mappings = GoogleSheetMapping.objects.filter(is_active=True)
        results = []
        
        for mapping in mappings:
            try:
                errors = mapping.validate_mappings()
                results.append({
                    'mapping_id': mapping.id,
                    'mapping_name': mapping.name,
                    'is_valid': len(errors) == 0,
                    'errors': errors
                })
            except Exception as e:
                results.append({
                    'mapping_id': mapping.id,
                    'mapping_name': mapping.name,
                    'is_valid': False,
                    'errors': [str(e)]
                })
        
        return {
            'success': True,
            'total_mappings': len(mappings),
            'results': results
        }
        
    except Exception as e:
        logger.error(f"خطأ في التحقق من التعيينات: {str(e)}")
        return {'success': False, 'error': str(e)}


def send_sync_notification(user_id, mapping, task, success=True, error=None):
    """
    إرسال إشعار بريد إلكتروني عن نتيجة المزامنة
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.get(id=user_id)
        if not user.email:
            return
        
        if success:
            subject = f"تمت مزامنة {mapping.name} بنجاح"
            message = f"""
            تم إكمال مزامنة "{mapping.name}" بنجاح.
            
            تفاصيل المهمة:
            - معرف المهمة: {task.id}
            - وقت البداية: {task.started_at}
            - وقت الانتهاء: {task.completed_at}
            - الصفوف المعالجة: {task.processed_rows}
            - الصفوف الناجحة: {task.successful_rows}
            - الصفوف الفاشلة: {task.failed_rows}
            
            يمكنك مراجعة التفاصيل من لوحة التحكم.
            """
        else:
            subject = f"فشلت مزامنة {mapping.name}"
            message = f"""
            فشلت مزامنة "{mapping.name}".
            
            تفاصيل الخطأ:
            {error or task.error_message}
            
            يرجى مراجعة الإعدادات والمحاولة مرة أخرى.
            """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True
        )
        
    except Exception as e:
        logger.error(f"خطأ في إرسال إشعار البريد الإلكتروني: {str(e)}")


# جدولة المهام الدورية
from celery.schedules import crontab
from django.conf import settings

# إضافة المهام المجدولة إلى إعدادات Celery
if hasattr(settings, 'CELERY_BEAT_SCHEDULE'):
    settings.CELERY_BEAT_SCHEDULE.update({
        'run-scheduled-syncs': {
            'task': 'odoo_db_manager.tasks.run_scheduled_syncs',
            'schedule': crontab(minute='*/5'),  # كل 5 دقائق
        },
        'cleanup-old-tasks': {
            'task': 'odoo_db_manager.tasks.cleanup_old_tasks',
            'schedule': crontab(hour=2, minute=0),  # يومياً في الساعة 2 صباحاً
        },
        'validate-mappings': {
            'task': 'odoo_db_manager.tasks.validate_all_mappings',
            'schedule': crontab(hour=1, minute=0),  # يومياً في الساعة 1 صباحاً
        },
    })
else:
    # إنشاء الجدولة إذا لم تكن موجودة
    settings.CELERY_BEAT_SCHEDULE = {
        'run-scheduled-syncs': {
            'task': 'odoo_db_manager.tasks.run_scheduled_syncs',
            'schedule': crontab(minute='*/5'),
        },
        'cleanup-old-tasks': {
            'task': 'odoo_db_manager.tasks.cleanup_old_tasks',
            'schedule': crontab(hour=2, minute=0),
        },
        'validate-mappings': {
            'task': 'odoo_db_manager.tasks.validate_all_mappings',
            'schedule': crontab(hour=1, minute=0),
        },
    }
