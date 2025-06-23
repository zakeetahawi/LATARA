"""
عروض مزامنة غوغل
"""

import os
import json
import logging
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from .google_sync import (
    GoogleSyncConfig, GoogleSyncLog, sync_with_google_sheets, sync_databases,
    sync_users, sync_customers, sync_orders, sync_products, sync_inspections, sync_settings, create_sheets_service
)
from .views import is_staff_or_superuser

from django.core.paginator import Paginator

# إعداد التسجيل
logger = logging.getLogger(__name__)

@login_required
@user_passes_test(is_staff_or_superuser)
def google_sync(request):
    """عرض صفحة مزامنة غوغل الرئيسية"""
    config = GoogleSyncConfig.get_active_config()
    all_logs = GoogleSyncLog.objects.all().order_by('-created_at')
    paginator = Paginator(all_logs, 5)
    page_number = request.GET.get('page', 1)
    sync_logs = paginator.get_page(page_number)
    next_sync = None
    if config and config.last_sync:
        next_sync = config.last_sync + datetime.timedelta(hours=config.sync_frequency)
    connection_status = False
    connection_status_cache_key = f'google_sync_connection_status_{config.id if config else "none"}'
    from django.core.cache import cache
    cached_status = cache.get(connection_status_cache_key)
    if cached_status is not None:
        connection_status = cached_status
    else:
        if config:
            try:
                credentials = config.get_credentials()
                if credentials:
                    sheets_service = create_sheets_service(credentials)
                    if sheets_service:
                        sheets_service.spreadsheets().get(spreadsheetId=config.spreadsheet_id).execute()
                        connection_status = True
            except Exception as e:
                logger.error(f"فشل اختبار الاتصال: {str(e)}")
        cache.set(connection_status_cache_key, connection_status, 600)
    context = {
        'title': 'مزامنة غوغل',
        'config': config,
        'sync_logs': sync_logs,
        'next_sync': next_sync,
        'connection_status': connection_status,
        'sync_success': request.session.pop('sync_success', False),
        'sync_results': request.session.pop('sync_results', {}),
        'sync_error': request.session.pop('sync_error', False),
        'sync_error_message': request.session.pop('sync_error_message', ''),
        'paginator': paginator,
        'page_obj': sync_logs,
    }
    return render(request, 'odoo_db_manager/google_sync.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
def google_sync_config(request):
    config = GoogleSyncConfig.get_active_config()
    scheduler_enabled = getattr(settings, 'GOOGLE_SYNC_SCHEDULER_ENABLED', False)
    scheduler_status = False
    scheduler_last_run = None
    try:
        from django_apscheduler.models import DjangoJobExecution
        job_executions = DjangoJobExecution.objects.filter(job_id='google_sync_job').order_by('-run_time')
        if job_executions.exists():
            scheduler_status = True
            scheduler_last_run = job_executions.first().run_time
    except Exception as e:
        logger.error(f"فشل التحقق من حالة المجدول: {str(e)}")
    keep_history = getattr(settings, 'GOOGLE_SYNC_KEEP_HISTORY', True)
    history_retention = getattr(settings, 'GOOGLE_SYNC_HISTORY_RETENTION', 30)
    context = {
        'title': 'إعدادات مزامنة غوغل',
        'config': config,
        'config_saved': request.session.pop('config_saved', False),
        'scheduler_enabled': scheduler_enabled,
        'scheduler_status': scheduler_status,
        'scheduler_last_run': scheduler_last_run,
        'keep_history': keep_history,
        'history_retention': history_retention,
    }
    return render(request, 'odoo_db_manager/google_sync_config.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
def google_sync_config_save(request):
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            spreadsheet_id = request.POST.get('spreadsheet_id')
            sync_frequency = int(request.POST.get('sync_frequency', 24))
            is_active = request.POST.get('is_active') == 'on'
            config = GoogleSyncConfig.get_active_config()
            if not config:
                config = GoogleSyncConfig()
            config.name = name
            config.spreadsheet_id = spreadsheet_id
            config.sync_frequency = sync_frequency
            config.is_active = is_active
            credentials_file = request.FILES.get('credentials_file')
            if credentials_file:
                if config.credentials_file:
                    try:
                        default_storage.delete(config.credentials_file.path)
                    except Exception as e:
                        logger.error(f"فشل حذف ملف بيانات الاعتماد القديم: {str(e)}")
                file_path = f'google_credentials/{credentials_file.name}'
                config.credentials_file.save(file_path, credentials_file)
            config.save()
            if is_active:
                GoogleSyncConfig.objects.exclude(id=config.id).update(is_active=False)
            messages.success(request, 'تم حفظ إعدادات مزامنة غوغل بنجاح')
            request.session['config_saved'] = True
            return redirect('odoo_db_manager:google_sync_config')
        except Exception as e:
            logger.error(f"حدث خطأ أثناء حفظ إعدادات مزامنة غوغل: {str(e)}")
            messages.error(request, f'حدث خطأ أثناء حفظ الإعدادات: {str(e)}')
            return redirect('odoo_db_manager:google_sync_config')
    return redirect('odoo_db_manager:google_sync_config')

@login_required
@user_passes_test(is_staff_or_superuser)
def google_sync_delete_credentials(request):
    try:
        config = GoogleSyncConfig.get_active_config()
        if config and config.credentials_file:
            default_storage.delete(config.credentials_file.path)
            config.credentials_file = None
            config.save()
            messages.success(request, 'تم حذف ملف بيانات الاعتماد بنجاح')
        else:
            messages.error(request, 'لا يوجد ملف بيانات اعتماد لحذفه')
    except Exception as e:
        logger.error(f"حدث خطأ أثناء حذف ملف بيانات الاعتماد: {str(e)}")
        messages.error(request, f'حدث خطأ أثناء حذف ملف بيانات الاعتماد: {str(e)}')
    return redirect('odoo_db_manager:google_sync_config')

@login_required
@user_passes_test(is_staff_or_superuser)
def google_sync_options(request):
    if request.method == 'POST':
        try:
            config = GoogleSyncConfig.get_active_config()
            if not config:
                messages.error(request, 'لا يوجد إعداد مزامنة نشط')
                return redirect('odoo_db_manager:google_sync')
            config.sync_databases = request.POST.get('sync_databases') == 'on'
            config.sync_users = request.POST.get('sync_users') == 'on'
            config.sync_customers = request.POST.get('sync_customers') == 'on'
            config.sync_orders = request.POST.get('sync_orders') == 'on'
            config.sync_products = request.POST.get('sync_products') == 'on'
            config.sync_settings = request.POST.get('sync_settings') == 'on'
            config.sync_frequency = int(request.POST.get('sync_frequency', 24))
            config.save()
            messages.success(request, 'تم حفظ خيارات المزامنة بنجاح')
        except Exception as e:
            logger.error(f"حدث خطأ أثناء حفظ خيارات المزامنة: {str(e)}")
            messages.error(request, f'حدث خطأ أثناء حفظ خيارات المزامنة: {str(e)}')
    return redirect('odoo_db_manager:google_sync')

@login_required
@user_passes_test(is_staff_or_superuser)
def google_sync_now(request):
    try:
        config = GoogleSyncConfig.get_active_config()
        if not config:
            messages.error(request, 'لا يوجد إعداد مزامنة نشط')
            return redirect('odoo_db_manager:google_sync')
        full_backup = bool(request.POST.get('full_backup'))
        selected_tables = request.POST.getlist('selected_tables')
        if selected_tables:
            full_backup = False
        start_time = datetime.datetime.now()
        try:
            result = sync_with_google_sheets(
                config_id=config.id,
                manual=True,
                full_backup=full_backup,
                selected_tables=selected_tables
            )
        except TypeError:
            result = sync_with_google_sheets(
                config_id=config.id,
                manual=True
            )
        end_time = datetime.datetime.now()
        duration = (end_time - start_time).total_seconds()
        if result['status'] == 'success':
            messages.success(request, 'تمت المزامنة مع Google Sheets بنجاح')
            request.session['sync_success'] = True
            total_items = 0
            for key, value in result.get('results', {}).items():
                if isinstance(value, dict) and 'message' in value:
                    import re
                    match = re.search(r'(\d+)', value['message'])
                    if match:
                        total_items += int(match.group(1))
            request.session['sync_results'] = {
                'total_items': total_items,
                'duration': round(duration, 2)
            }
        else:
            messages.error(request, f'فشلت المزامنة مع Google Sheets: {result["message"]}')
            request.session['sync_error'] = True
            request.session['sync_error_message'] = result['message']
    except Exception as e:
        logger.error(f"حدث خطأ أثناء تنفيذ المزامنة: {str(e)}")
        messages.error(request, f'حدث خطأ أثناء تنفيذ المزامنة: {str(e)}')
        request.session['sync_error'] = True
        request.session['sync_error_message'] = str(e)
    return redirect('odoo_db_manager:google_sync')

@login_required
@user_passes_test(is_staff_or_superuser)
def google_sync_test(request):
    try:
        config = GoogleSyncConfig.get_active_config()
        if not config:
            messages.error(request, 'لا يوجد إعداد مزامنة نشط')
            return redirect('odoo_db_manager:google_sync')
        credentials = config.get_credentials()
        if not credentials:
            messages.error(request, 'لا يمكن قراءة بيانات الاعتماد')
            return redirect('odoo_db_manager:google_sync')
        sheets_service = create_sheets_service(credentials)
        if not sheets_service:
            messages.error(request, f"فشل إنشاء خدمة Google Sheets. تحقق من صحة بيانات الاعتماد ومشاركة جدول البيانات مع البريد: {credentials.get('client_email', 'غير معروف')}")
            return redirect('odoo_db_manager:google_sync')
        spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=config.spreadsheet_id).execute()
        spreadsheet_title = spreadsheet.get('properties', {}).get('title', 'جدول بيانات')
        messages.success(request, f'تم الاتصال بنجاح بجدول البيانات "{spreadsheet_title}"')
    except Exception as e:
        logger.error(f"فشل اختبار الاتصال: {str(e)}")
        messages.error(request, f'فشل الاتصال بـ Google Sheets: {str(e)}')
    return redirect('odoo_db_manager:google_sync')

@login_required
@user_passes_test(is_staff_or_superuser)
def google_sync_reset(request):
    config = GoogleSyncConfig.get_active_config()
    if not config:
        messages.error(request, 'لا يوجد إعداد مزامنة نشط')
        return redirect('odoo_db_manager:google_sync')
    from django.db import transaction
    with transaction.atomic():
        GoogleSyncLog.objects.filter(config=config).delete()
        GoogleSyncLog.objects.create(
            config=config,
            status='info',
            message='تم حذف سجلات المزامنة القديمة. سجل جديد تم إنشاؤه.'
        )
    messages.success(request, 'تم حذف سجلات المزامنة القديمة وإنشاء سجل جديد')
    return redirect('odoo_db_manager:google_sync')

@login_required
@user_passes_test(is_staff_or_superuser)
@require_POST
@csrf_exempt
def google_sync_advanced_settings(request):
    try:
        data = json.loads(request.body)
        enable_scheduler = data.get('enable_scheduler', False)
        keep_history = data.get('keep_history', True)
        history_retention = int(data.get('history_retention', 30))
        settings_file = os.path.join(settings.BASE_DIR, 'google_sync_settings.json')
        settings_data = {
            'enable_scheduler': enable_scheduler,
            'keep_history': keep_history,
            'history_retention': history_retention,
            'updated_at': timezone.now().isoformat()
        }
        with open(settings_file, 'w') as f:
            json.dump(settings_data, f, indent=4)
        setattr(settings, 'GOOGLE_SYNC_SCHEDULER_ENABLED', enable_scheduler)
        setattr(settings, 'GOOGLE_SYNC_KEEP_HISTORY', keep_history)
        setattr(settings, 'GOOGLE_SYNC_HISTORY_RETENTION', history_retention)
        if enable_scheduler:
            try:
                from django_apscheduler.models import DjangoJob
                from apscheduler.triggers.interval import IntervalTrigger
                from django_apscheduler.jobstores import DjangoJobStore
                from apscheduler.schedulers.background import BackgroundScheduler
                scheduler = BackgroundScheduler()
                scheduler.add_jobstore(DjangoJobStore(), 'default')
                job = scheduler.add_job(
                    sync_with_google_sheets,
                    trigger=IntervalTrigger(hours=24),
                    id='google_sync_job',
                    replace_existing=True
                )
                scheduler.start()
            except Exception as e:
                logger.error(f"فشل تفعيل المجدول: {str(e)}")
        else:
            try:
                from django_apscheduler.models import DjangoJob
                DjangoJob.objects.filter(id='google_sync_job').delete()
            except Exception as e:
                logger.error(f"فشل تعطيل المجدول: {str(e)}")
        if keep_history and history_retention > 0:
            delete_date = timezone.now() - datetime.timedelta(days=history_retention)
            GoogleSyncLog.objects.filter(created_at__lt=delete_date).delete()
        return JsonResponse({'status': 'success', 'message': 'تم حفظ الإعدادات المتقدمة بنجاح'})
    except Exception as e:
        logger.error(f"فشل حفظ الإعدادات المتقدمة: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)})

@login_required
@user_passes_test(is_staff_or_superuser)
def google_sync_logs_api(request):
    logs = GoogleSyncLog.objects.all().order_by('-created_at')[:50]
    logs_data = []
    for log in logs:
        details = ''
        if log.details:
            try:
                import json
                details = json.dumps(log.details, indent=2, ensure_ascii=False)
            except Exception:
                details = str(log.details)
        logs_data.append({
            'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'status': log.get_status_display(),
            'message': log.message,
            'details': details
        })
    return JsonResponse({'logs': logs_data})
