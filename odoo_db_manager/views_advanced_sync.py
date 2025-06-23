"""
Views للمزامنة المتقدمة مع Google Sheets
Advanced Google Sheets Sync Views
"""

import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from .google_sync_advanced import (
    GoogleSheetMapping, GoogleSyncTask, GoogleSyncConflict, GoogleSyncSchedule
)
from .advanced_sync_service import AdvancedSyncService
from .google_sheets_import import GoogleSheetsImporter
from .views import is_staff_or_superuser

logger = logging.getLogger(__name__)


def _translate_column_name(column_name):
    """
    ترجمة اسم العمود من الإنجليزية إلى العربية
    Translate column name from English to Arabic
    """
    if not column_name:
        return ""

    # قاموس ترجمة أسماء الأعمدة
    translations = {
        # معلومات العميل
        'id': 'معرف العميل',
        'code': 'رمز العميل',
        'name': 'اسم العميل',
        'phone': 'رقم الهاتف',
        'phone2': 'رقم هاتف إضافي',
        'email': 'البريد الإلكتروني',
        'address': 'العنوان',
        'customer_type': 'نوع العميل',
        'category_display': 'فئة العميل',
        'branch_display': 'الفرع',
        'interests': 'الاهتمامات',
        'status': 'الحالة',
        'notes': 'ملاحظات',
        'created_by_display': 'أنشئ بواسطة',
        'created_at': 'تاريخ الإنشاء',
        'updated_at': 'تاريخ التحديث',

        # معلومات الطلبات
        'order_number': 'رقم الطلب',
        'invoice_number': 'رقم الفاتورة',
        'contract_number': 'رقم العقد',
        'total_amount': 'المبلغ الإجمالي',
        'paid_amount': 'المبلغ المدفوع',
        'remaining_amount': 'المبلغ المتبقي',
        'order_status': 'حالة الطلب',
        'order_date': 'تاريخ الطلب',
        'delivery_date': 'تاريخ التسليم',
        'salesperson': 'البائع',
        'salesperson_display': 'البائع',

        # معلومات المنتجات
        'product_name': 'اسم المنتج',
        'product_type': 'نوع المنتج',
        'quantity': 'الكمية',
        'unit_price': 'سعر الوحدة',
        'discount': 'الخصم',
        'tax': 'الضريبة',

        # معلومات عامة
        'description': 'الوصف',
        'image': 'الصورة',
        'active': 'نشط',
        'priority': 'الأولوية',
        'reference': 'المرجع',
        'source': 'المصدر',
        'type': 'النوع',
        'category': 'الفئة',
        'tags': 'العلامات',
        'location': 'الموقع',
        'city': 'المدينة',
        'country': 'البلد',
        'website': 'الموقع الإلكتروني',
        'company': 'الشركة',
        'department': 'القسم',
        'position': 'المنصب',
        'title': 'اللقب',
        'gender': 'الجنس',
        'birth_date': 'تاريخ الميلاد',
        'age': 'العمر',
    }

    # إرجاع الترجمة إن وجدت، وإلا الاسم الأصلي
    return translations.get(column_name.lower(), column_name)


@login_required
@user_passes_test(is_staff_or_superuser)
def advanced_sync_dashboard(request):
    """لوحة تحكم المزامنة المتقدمة"""
    try:
        # إحصائيات عامة
        total_mappings = GoogleSheetMapping.objects.count()
        active_mappings = GoogleSheetMapping.objects.filter(is_active=True).count()
        total_tasks = GoogleSyncTask.objects.count()
        pending_conflicts = GoogleSyncConflict.objects.filter(resolution_status='pending').count()

        # آخر المهام
        recent_tasks = GoogleSyncTask.objects.select_related('mapping').order_by('-created_at')[:10]

        # التعيينات النشطة
        active_mappings_list = GoogleSheetMapping.objects.filter(is_active=True).order_by('-last_sync')[:5]

        # المزامنة المجدولة
        scheduled_syncs = GoogleSyncSchedule.objects.filter(is_active=True).select_related('mapping')

        context = {
            'total_mappings': total_mappings,
            'active_mappings': active_mappings,
            'total_tasks': total_tasks,
            'pending_conflicts': pending_conflicts,
            'recent_tasks': recent_tasks,
            'active_mappings_list': active_mappings_list,
            'scheduled_syncs': scheduled_syncs,
        }

        return render(request, 'odoo_db_manager/advanced_sync/dashboard.html', context)

    except Exception as e:
        logger.error(f"خطأ في لوحة تحكم المزامنة المتقدمة: {str(e)}")
        messages.error(request, f"حدث خطأ: {str(e)}")
        return redirect('odoo_db_manager:index')


@login_required
@user_passes_test(is_staff_or_superuser)
def mapping_list(request):
    """قائمة تعيينات Google Sheets"""
    try:
        mappings = GoogleSheetMapping.objects.all().order_by('-created_at')

        # البحث
        search_query = request.GET.get('search', '')
        if search_query:
            mappings = mappings.filter(name__icontains=search_query)

        # التصفية
        status_filter = request.GET.get('status', '')
        if status_filter == 'active':
            mappings = mappings.filter(is_active=True)
        elif status_filter == 'inactive':
            mappings = mappings.filter(is_active=False)

        # الترقيم
        paginator = Paginator(mappings, 20)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'search_query': search_query,
            'status_filter': status_filter,
        }

        return render(request, 'odoo_db_manager/advanced_sync/mapping_list.html', context)

    except Exception as e:
        logger.error(f"خطأ في قائمة التعيينات: {str(e)}")
        messages.error(request, f"حدث خطأ: {str(e)}")
        return redirect('odoo_db_manager:advanced_sync_dashboard')


@login_required
@user_passes_test(is_staff_or_superuser)
def mapping_create(request):
    """إنشاء تعيين جديد"""
    if request.method == 'POST':
        try:
            spreadsheet_id = request.POST.get('spreadsheet_id')
            sheet_name = request.POST.get('sheet_name')

            # التحقق من وجود تعيين مكرر
            existing_mapping = GoogleSheetMapping.objects.filter(
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name
            ).first()

            if existing_mapping:
                messages.error(
                    request,
                    f'يوجد تعيين بالفعل لهذا الجدول والصفحة: "{existing_mapping.name}". '
                    f'يمكنك تعديل التعيين الموجود أو حذفه أولاً.'
                )
                # إعادة توجيه إلى صفحة التعيين الموجود
                return redirect('odoo_db_manager:mapping_detail', mapping_id=existing_mapping.id)

            with transaction.atomic():
                # حفظ القيم الافتراضية
                default_customer_category_id = request.POST.get('default_customer_category')
                default_branch_id = request.POST.get('default_branch')

                # جلب تعيينات الأعمدة من النموذج
                column_mappings = {}
                for key, value in request.POST.items():
                    if key.startswith('column_'):
                        column_name = key.replace('column_', '')
                        if value and value != 'ignore':
                            column_mappings[column_name] = value

                # حماية: تحويل أي اسم عمود إلى رقم العمود الصحيح
                headers = []
                try:
                    importer = GoogleSheetsImporter()
                    importer.initialize()
                    headers = importer.get_sheet_data(sheet_name)[int(request.POST.get('header_row', 1)) - 1]
                except Exception:
                    pass
                new_mappings = {}
                changed = False
                for k, v in column_mappings.items():
                    if headers and k in headers:
                        col_index = headers.index(k)
                        new_mappings[str(col_index)] = v
                        changed = True
                    else:
                        new_mappings[str(k)] = v
                if changed:
                    messages.info(request, 'تم تحويل أسماء الأعمدة إلى أرقام تلقائيًا لضمان سلامة المزامنة.')
                # إنشاء التعيين
                mapping = GoogleSheetMapping.objects.create(
                    name=request.POST.get('name'),
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name,
                    header_row=int(request.POST.get('header_row', 1)),
                    start_row=int(request.POST.get('start_row', 2)),
                    column_mappings=new_mappings,  # حفظ تعيينات الأعمدة
                    auto_create_customers=request.POST.get('auto_create_customers') == 'on',
                    auto_create_orders=request.POST.get('auto_create_orders') == 'on',
                    auto_create_inspections=request.POST.get('auto_create_inspections') == 'on',
                    auto_create_installations=request.POST.get('auto_create_installations') == 'on',
                    update_existing_customers=request.POST.get('update_existing_customers') == 'on',
                    update_existing_orders=request.POST.get('update_existing_orders') == 'on',
                    enable_reverse_sync=request.POST.get('enable_reverse_sync') == 'on',
                    # القيم الافتراضية
                    default_customer_category_id=default_customer_category_id if default_customer_category_id else None,
                    default_customer_type=request.POST.get('default_customer_type') or None,
                    default_branch_id=default_branch_id if default_branch_id else None,
                    use_current_date_as_created=request.POST.get('use_current_date_as_created') == 'on',
                    created_by=request.user
                )

                messages.success(request, f"تم إنشاء التعيين '{mapping.name}' بنجاح")
                return redirect('odoo_db_manager:mapping_detail', mapping_id=mapping.id)

        except Exception as e:
            logger.error(f"خطأ في إنشاء التعيين: {str(e)}")
            messages.error(request, f"حدث خطأ في إنشاء التعيين: {str(e)}")

    # جلب قائمة الجداول المتاحة
    try:
        importer = GoogleSheetsImporter()
        importer.initialize()
        available_sheets = importer.get_available_sheets()
    except Exception as e:
        logger.error(f"خطأ في جلب قائمة الجداول: {str(e)}")
        available_sheets = []
        messages.warning(request, "لا يمكن جلب قائمة الجداول. تأكد من إعدادات Google Sheets.")

    import json

    # جلب البيانات المطلوبة للقوائم المنسدلة
    from customers.models import CustomerCategory
    from accounts.models import Branch

    customer_categories = CustomerCategory.objects.all().order_by('name')
    branches = Branch.objects.all().order_by('name')

    context = {
        'available_sheets': available_sheets,
        'field_types': GoogleSheetMapping.FIELD_TYPES,
        'field_types_json': json.dumps(GoogleSheetMapping.FIELD_TYPES, ensure_ascii=False),
        'customer_categories': customer_categories,
        'branches': branches,
    }

    return render(request, 'odoo_db_manager/advanced_sync/mapping_create.html', context)


@login_required
@user_passes_test(is_staff_or_superuser)
def mapping_detail(request, mapping_id):
    """تفاصيل التعيين"""
    try:
        mapping = get_object_or_404(GoogleSheetMapping, id=mapping_id)

        # جلب عناوين الأعمدة من Google Sheets
        try:
            importer = GoogleSheetsImporter()
            importer.initialize()

            # تحديث معرف الجدول إلى معرف التعيين
            original_id = getattr(importer.config, 'spreadsheet_id', None)
            if hasattr(importer.config, 'spreadsheet_id'):
                importer.config.spreadsheet_id = mapping.spreadsheet_id

            sheet_data = importer.get_sheet_data(mapping.sheet_name)
            headers = sheet_data[mapping.header_row - 1] if sheet_data and len(sheet_data) >= mapping.header_row else []

            # استعادة المعرف الأصلي
            if original_id and hasattr(importer.config, 'spreadsheet_id'):
                importer.config.spreadsheet_id = original_id
        except Exception as e:
            logger.error(f"خطأ في جلب عناوين الأعمدة: {str(e)}")
            headers = []
            messages.warning(request, "لا يمكن جلب عناوين الأعمدة من Google Sheets")

        # آخر المهام
        recent_tasks = GoogleSyncTask.objects.filter(mapping=mapping).order_by('-created_at')[:10]

        # التعارضات المعلقة
        pending_conflicts = GoogleSyncConflict.objects.filter(
            task__mapping=mapping,
            resolution_status='pending'
        ).order_by('-created_at')[:10]

        # الجدولة
        schedule = GoogleSyncSchedule.objects.filter(mapping=mapping).first()

        context = {
            'mapping': mapping,
            'headers': headers,
            'recent_tasks': recent_tasks,
            'pending_conflicts': pending_conflicts,
            'schedule': schedule,
            'field_types': GoogleSheetMapping.FIELD_TYPES,
        }

        return render(request, 'odoo_db_manager/advanced_sync/mapping_detail.html', context)

    except Exception as e:
        logger.error(f"خطأ في تفاصيل التعيين: {str(e)}")
        messages.error(request, f"حدث خطأ: {str(e)}")
        return redirect('odoo_db_manager:mapping_list')


@login_required
@user_passes_test(is_staff_or_superuser)
def mapping_edit(request, mapping_id):
    """تعديل تعيين مزامنة"""
    try:
        mapping = get_object_or_404(GoogleSheetMapping, id=mapping_id)

        if request.method == 'POST':
            # تحديث بيانات التعيين
            mapping.name = request.POST.get('name', mapping.name)
            mapping.spreadsheet_id = request.POST.get('spreadsheet_id', mapping.spreadsheet_id)
            mapping.sheet_name = request.POST.get('sheet_name', mapping.sheet_name)
            mapping.header_row = int(request.POST.get('header_row', mapping.header_row))
            mapping.start_row = int(request.POST.get('start_row', mapping.start_row))

            # إعدادات المزامنة
            mapping.auto_create_customers = request.POST.get('auto_create_customers') == 'on'
            mapping.auto_create_orders = request.POST.get('auto_create_orders') == 'on'
            mapping.update_existing_customers = request.POST.get('update_existing_customers') == 'on'
            mapping.update_existing_orders = request.POST.get('update_existing_orders') == 'on'
            mapping.enable_reverse_sync = request.POST.get('enable_reverse_sync') == 'on'

            # القيم الافتراضية
            default_customer_category_id = request.POST.get('default_customer_category')
            mapping.default_customer_category_id = default_customer_category_id if default_customer_category_id else None
            mapping.default_customer_type = request.POST.get('default_customer_type') or None
            default_branch_id = request.POST.get('default_branch')
            mapping.default_branch_id = default_branch_id if default_branch_id else None
            mapping.use_current_date_as_created = request.POST.get('use_current_date_as_created') == 'on'

            mapping.save()
            messages.success(request, f"تم تحديث التعيين '{mapping.name}' بنجاح")
            return redirect('odoo_db_manager:mapping_detail', mapping_id=mapping.id)

        # جلب قائمة الجداول المتاحة
        try:
            from .google_sheets_import import GoogleSheetsImporter
            importer = GoogleSheetsImporter()
            importer.initialize()
            available_sheets = importer.get_available_sheets()
        except Exception as e:
            logger.error(f"خطأ في جلب قائمة الجداول: {str(e)}")
            available_sheets = []
            messages.warning(request, "لا يمكن جلب قائمة الجداول. تأكد من إعدادات Google Sheets.")

        # جلب البيانات المطلوبة للقوائم المنسدلة
        from customers.models import CustomerCategory
        from accounts.models import Branch

        customer_categories = CustomerCategory.objects.all().order_by('name')
        branches = Branch.objects.all().order_by('name')

        context = {
            'mapping': mapping,
            'available_sheets': available_sheets,
            'field_types': GoogleSheetMapping.FIELD_TYPES,
            'customer_categories': customer_categories,
            'branches': branches,
        }

        return render(request, 'odoo_db_manager/advanced_sync/mapping_edit.html', context)

    except Exception as e:
        logger.error(f"خطأ في تعديل التعيين: {str(e)}")
        messages.error(request, f"حدث خطأ: {str(e)}")
        return redirect('odoo_db_manager:mapping_list')


@login_required
@user_passes_test(is_staff_or_superuser)
def mapping_delete(request, mapping_id):
    """حذف تعيين مزامنة"""
    try:
        mapping = GoogleSheetMapping.objects.get(id=mapping_id)
        mapping_name = mapping.name
        mapping.delete()

        messages.success(request, f'تم حذف تعيين "{mapping_name}" بنجاح')
        return redirect('odoo_db_manager:mapping_list')

    except GoogleSheetMapping.DoesNotExist:
        messages.error(request, 'لم يتم العثور على التعيين المطلوب')
        return redirect('odoo_db_manager:mapping_list')
    except Exception as e:
        logger.error(f"خطأ في حذف التعيين: {str(e)}")
        messages.error(request, f'حدث خطأ في حذف التعيين: {str(e)}')
        return redirect('odoo_db_manager:mapping_list')


@login_required
@user_passes_test(is_staff_or_superuser)
@require_http_methods(["POST"])
def api_run_sync(request, mapping_id):
    """تشغيل مزامنة عبر API"""
    try:
        mapping = get_object_or_404(GoogleSheetMapping, id=mapping_id)

        # إنشاء مهمة مزامنة
        task = GoogleSyncTask.objects.create(
            mapping=mapping,
            status='pending',
            created_by=request.user
        )

        # بدء المزامنة الفعلية
        try:
            task.status = 'running'
            task.save()

            # إنشاء importer مع معرف الجدول الصحيح
            importer = GoogleSheetsImporter()
            importer.initialize()

            # حفظ المعرف الأصلي وتحديثه بمعرف التعيين
            original_id = getattr(importer.config, 'spreadsheet_id', None)

            try:
                # تحديث معرف الجدول إلى معرف التعيين
                if hasattr(importer.config, 'spreadsheet_id'):
                    importer.config.spreadsheet_id = mapping.spreadsheet_id

                # جلب بيانات الجدول
                sheet_data = importer.get_sheet_data(mapping.sheet_name)

                if not sheet_data:
                    raise Exception('لا توجد بيانات في الجدول')

                # تنفيذ المزامنة باستخدام الخدمة المتقدمة
                from .google_sync_advanced import AdvancedSyncService
                sync_service = AdvancedSyncService(mapping)
                result = sync_service.sync_from_sheets(task)

                # تحديث حالة المهمة
                task.status = 'completed'
                task.result = f"تم استيراد {result.get('imported', 0)} سجل وتحديث {result.get('updated', 0)} سجل"
                task.save()

                # تحديث تاريخ آخر مزامنة
                from django.utils import timezone
                mapping.last_sync = timezone.now()
                mapping.save(update_fields=['last_sync'])

            finally:
                # استعادة المعرف الأصلي
                if original_id and hasattr(importer.config, 'spreadsheet_id'):
                    importer.config.spreadsheet_id = original_id

            return JsonResponse({
                'success': True,
                'task_id': task.id,
                'message': 'تم بدء المزامنة بنجاح',
                'result': task.result
            })

        except Exception as sync_error:
            logger.error(f"خطأ في المزامنة: {str(sync_error)}")
            task.status = 'failed'
            task.error_message = str(sync_error)
            task.result = f'فشلت المزامنة: {str(sync_error)}'
            task.save()

            return JsonResponse({
                'success': False,
                'error': f'فشلت المزامنة: {str(sync_error)}',
                'task_id': task.id,
                'message': f'فشلت المزامنة: {str(sync_error)}'
            })

    except Exception as e:
        logger.error(f"خطأ في API تشغيل المزامنة: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@user_passes_test(is_staff_or_superuser)
def get_sheets_by_id(request):
    """جلب أسماء الصفحات من جدول محدد"""
    try:
        spreadsheet_id = request.GET.get('spreadsheet_id')

        if not spreadsheet_id:
            return JsonResponse({
                'success': False,
                'error': 'معرف الجدول مطلوب'
            })

        # إنشاء importer مع معرف الجدول المحدد
        importer = GoogleSheetsImporter()
        importer.initialize()

        # حفظ المعرف الأصلي وتحديثه مؤقتاً
        original_id = getattr(importer.config, 'spreadsheet_id', None)

        try:
            # تحديث معرف الجدول مباشرة
            if hasattr(importer.config, 'spreadsheet_id'):
                importer.config.spreadsheet_id = spreadsheet_id

            # جلب قائمة الصفحات مع المعرف الجديد
            sheets = importer.get_available_sheets()

            return JsonResponse({
                'success': True,
                'sheets': sheets
            })

        finally:
            # استعادة المعرف الأصلي
            if original_id and hasattr(importer.config, 'spreadsheet_id'):
                importer.config.spreadsheet_id = original_id

    except Exception as e:
        logger.error(f"خطأ في جلب صفحات الجدول: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب صفحات الجدول: {str(e)}'
        })


@login_required
@user_passes_test(is_staff_or_superuser)
def mapping_update_columns(request, mapping_id):
    """تحديث تعيين الأعمدة"""
    try:
        mapping = get_object_or_404(GoogleSheetMapping, id=mapping_id)

        if request.method == 'GET':
            # عرض صفحة تحديث التعيينات
            import json
            context = {
                'mapping': mapping,
                'field_types': GoogleSheetMapping.FIELD_TYPES,
                'field_types_json': json.dumps(GoogleSheetMapping.FIELD_TYPES, ensure_ascii=False),
            }
            return render(request, 'odoo_db_manager/advanced_sync/mapping_update_columns.html', context)

        # جلب تعيينات الأعمدة من النموذج
        column_mappings = {}
        for key, value in request.POST.items():
            if key.startswith('column_'):
                column_name = key.replace('column_', '')
                if value and value != 'ignore':
                    column_mappings[column_name] = value

        # حماية: تحويل أي اسم عمود إلى رقم العمود الصحيح
        headers = []
        try:
            importer = GoogleSheetsImporter()
            importer.initialize()
            headers = importer.get_sheet_data(mapping.sheet_name)[mapping.header_row - 1]
        except Exception:
            pass
        new_mappings = {}
        changed = False
        for k, v in column_mappings.items():
            if headers and k in headers:
                col_index = headers.index(k)
                new_mappings[str(col_index)] = v
                changed = True
            else:
                new_mappings[str(k)] = v
        if changed:
            messages.info(request, 'تم تحويل أسماء الأعمدة إلى أرقام تلقائيًا لضمان سلامة المزامنة.')
        # التحقق من صحة التعيينات
        mapping.column_mappings = new_mappings
        errors = mapping.validate_mappings()

        if errors:
            messages.error(request, f"أخطاء في التعيين: {', '.join(errors)}")
        else:
            mapping.save(update_fields=['column_mappings'])
            messages.success(request, "تم تحديث تعيين الأعمدة بنجاح")

        return redirect('odoo_db_manager:mapping_detail', mapping_id=mapping.id)

    except Exception as e:
        logger.error(f"خطأ في تحديث تعيين الأعمدة: {str(e)}")
        messages.error(request, f"حدث خطأ: {str(e)}")
        return redirect('odoo_db_manager:mapping_list')


@login_required
@user_passes_test(is_staff_or_superuser)
@require_http_methods(["POST"])
def start_sync(request, mapping_id):
    """بدء المزامنة"""
    try:
        mapping = get_object_or_404(GoogleSheetMapping, id=mapping_id)

        # التحقق من وجود تعيينات الأعمدة
        if not mapping.column_mappings:
            return JsonResponse({
                'success': False,
                'error': 'يجب تحديد تعيينات الأعمدة أولاً. انتقل إلى صفحة تفاصيل التعيين وقم بتحديد تعيينات الأعمدة.'
            })

        # التحقق من صحة التعيينات
        errors = mapping.validate_mappings()
        if errors:
            return JsonResponse({
                'success': False,
                'error': f"أخطاء في التعيين: {', '.join(errors)}"
            })

        # إنشاء مهمة المزامنة
        task = GoogleSyncTask.objects.create(
            mapping=mapping,
            task_type='import',
            created_by=request.user
        )

        # بدء المهمة
        task.start_task()

        # تنفيذ المزامنة
        sync_service = AdvancedSyncService(mapping)
        result = sync_service.sync_from_sheets(task)

        if result['success']:
            # تحديث المهمة بالنتائج
            task.mark_completed(result)

            return JsonResponse({
                'success': True,
                'task_id': task.id,
                'stats': result['stats'],
                'conflicts': result.get('conflicts', 0),
                'message': f"تمت المزامنة بنجاح! تم معالجة {result['stats']['processed_rows']} صف"
            })
        else:
            # تحديث المهمة بالفشل
            task.mark_failed(result.get('error', 'خطأ غير معروف'))

            return JsonResponse({
                'success': False,
                'error': result.get('error', 'خطأ غير معروف')
            })

    except Exception as e:
        logger.error(f"خطأ في بدء المزامنة: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@user_passes_test(is_staff_or_superuser)
def task_detail(request, task_id):
    """تفاصيل المهمة"""
    try:
        task = get_object_or_404(GoogleSyncTask, id=task_id)

        # التعارضات المرتبطة بالمهمة
        conflicts = GoogleSyncConflict.objects.filter(task=task).order_by('-created_at')

        context = {
            'task': task,
            'conflicts': conflicts,
        }

        return render(request, 'odoo_db_manager/advanced_sync/task_detail.html', context)

    except Exception as e:
        logger.error(f"خطأ في تفاصيل المهمة: {str(e)}")
        messages.error(request, f"حدث خطأ: {str(e)}")
        return redirect('odoo_db_manager:advanced_sync_dashboard')


@login_required
@user_passes_test(is_staff_or_superuser)
def conflict_list(request):
    """قائمة التعارضات"""
    try:
        conflicts = GoogleSyncConflict.objects.select_related('task', 'task__mapping').order_by('-created_at')

        # التصفية
        status_filter = request.GET.get('status', '')
        if status_filter:
            conflicts = conflicts.filter(resolution_status=status_filter)

        type_filter = request.GET.get('type', '')
        if type_filter:
            conflicts = conflicts.filter(conflict_type=type_filter)

        # الترقيم
        paginator = Paginator(conflicts, 20)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'status_filter': status_filter,
            'type_filter': type_filter,
            'conflict_types': GoogleSyncConflict.CONFLICT_TYPES,
            'resolution_statuses': GoogleSyncConflict.RESOLUTION_STATUS,
        }

        return render(request, 'odoo_db_manager/advanced_sync/conflict_list.html', context)

    except Exception as e:
        logger.error(f"خطأ في قائمة التعارضات: {str(e)}")
        messages.error(request, f"حدث خطأ: {str(e)}")
        return redirect('odoo_db_manager:advanced_sync_dashboard')


@login_required
@user_passes_test(is_staff_or_superuser)
@require_http_methods(["POST"])
def resolve_conflict(request, conflict_id):
    """حل التعارض"""
    try:
        conflict = get_object_or_404(GoogleSyncConflict, id=conflict_id)

        resolution_status = request.POST.get('resolution_status')
        notes = request.POST.get('notes', '')

        if resolution_status in dict(GoogleSyncConflict.RESOLUTION_STATUS):
            conflict.resolve_conflict(resolution_status, request.user, notes)
            messages.success(request, "تم حل التعارض بنجاح")
        else:
            messages.error(request, "حالة الحل غير صحيحة")

        return redirect('odoo_db_manager:conflict_list')

    except Exception as e:
        logger.error(f"خطأ في حل التعارض: {str(e)}")
        messages.error(request, f"حدث خطأ: {str(e)}")
        return redirect('odoo_db_manager:conflict_list')


@login_required
@user_passes_test(is_staff_or_superuser)
def schedule_sync(request, mapping_id):
    """جدولة المزامنة"""
    try:
        mapping = get_object_or_404(GoogleSheetMapping, id=mapping_id)

        if request.method == 'POST':
            frequency_minutes = int(request.POST.get('frequency_minutes', 60))
            is_active = request.POST.get('is_active') == 'on'

            # إنشاء أو تحديث الجدولة
            schedule, created = GoogleSyncSchedule.objects.get_or_create(
                mapping=mapping,
                defaults={
                    'frequency_minutes': frequency_minutes,
                    'is_active': is_active,
                    'created_by': request.user
                }
            )

            if not created:
                schedule.frequency_minutes = frequency_minutes
                schedule.is_active = is_active
                schedule.save(update_fields=['frequency_minutes', 'is_active'])

            # حساب موعد التشغيل القادم
            schedule.calculate_next_run()

            action = "تم إنشاء" if created else "تم تحديث"
            messages.success(request, f"{action} جدولة المزامنة بنجاح")

            return redirect('odoo_db_manager:mapping_detail', mapping_id=mapping.id)

        # جلب الجدولة الحالية إن وجدت
        schedule = GoogleSyncSchedule.objects.filter(mapping=mapping).first()

        context = {
            'mapping': mapping,
            'schedule': schedule,
            'frequency_choices': GoogleSyncSchedule.FREQUENCY_CHOICES,
        }

        return render(request, 'odoo_db_manager/advanced_sync/schedule_sync.html', context)

    except Exception as e:
        logger.error(f"خطأ في جدولة المزامنة: {str(e)}")
        messages.error(request, f"حدث خطأ: {str(e)}")
        return redirect('odoo_db_manager:mapping_detail', mapping_id=mapping_id)


@login_required
@user_passes_test(is_staff_or_superuser)
def get_sheet_columns(request):
    """جلب أعمدة الجدول عبر AJAX"""
    try:
        spreadsheet_id = request.GET.get('spreadsheet_id')
        sheet_name = request.GET.get('sheet_name')
        header_row = int(request.GET.get('header_row', 1))

        if not spreadsheet_id or not sheet_name:
            return JsonResponse({
                'success': False,
                'error': 'معرف الجدول واسم الصفحة مطلوبان'
            })

        # جلب البيانات
        importer = GoogleSheetsImporter()
        importer.initialize()

        # تحديث معرف الجدول مؤقتاً
        original_id = importer.config.spreadsheet_id
        importer.config.spreadsheet_id = spreadsheet_id

        try:
            sheet_data = importer.get_sheet_data(sheet_name)
            headers = sheet_data[header_row - 1] if sheet_data and len(sheet_data) >= header_row else []

            # ترجمة أسماء الأعمدة إلى العربية
            translated_headers = []
            for header in headers:
                translated = _translate_column_name(header)
                translated_headers.append({
                    'original': header,
                    'translated': translated,
                    'display': f"{translated} ({header})" if translated != header else header
                })

            return JsonResponse({
                'success': True,
                'headers': translated_headers
            })
        finally:
            # استعادة المعرف الأصلي
            importer.config.spreadsheet_id = original_id

    except Exception as e:
        logger.error(f"خطأ في جلب أعمدة الجدول: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@user_passes_test(is_staff_or_superuser)
def preview_sheet_data(request):
    """معاينة بيانات الجدول"""
    try:
        spreadsheet_id = request.GET.get('spreadsheet_id')
        sheet_name = request.GET.get('sheet_name')
        header_row = int(request.GET.get('header_row', 1))
        start_row = int(request.GET.get('start_row', 2))

        if not spreadsheet_id or not sheet_name:
            return JsonResponse({
                'success': False,
                'error': 'معرف الجدول واسم الصفحة مطلوبان'
            })

        # جلب البيانات
        importer = GoogleSheetsImporter()
        importer.initialize()

        # تحديث معرف الجدول مؤقتاً
        original_id = importer.config.spreadsheet_id
        importer.config.spreadsheet_id = spreadsheet_id

        try:
            sheet_data = importer.get_sheet_data(sheet_name)

            if not sheet_data or len(sheet_data) < start_row:
                return JsonResponse({
                    'success': False,
                    'error': 'لا توجد بيانات كافية في الجدول'
                })

            headers = sheet_data[header_row - 1] if len(sheet_data) >= header_row else []
            preview_data = sheet_data[start_row - 1:start_row + 4]  # أول 5 صفوف

            return JsonResponse({
                'success': True,
                'headers': headers,
                'data': preview_data,
                'total_rows': len(sheet_data) - start_row + 1
            })
        finally:
            # استعادة المعرف الأصلي
            importer.config.spreadsheet_id = original_id

    except Exception as e:
        logger.error(f"خطأ في معاينة بيانات الجدول: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
@user_passes_test(is_staff_or_superuser)
def get_task_status(request, task_id):
    """جلب حالة المهمة عبر AJAX"""
    try:
        task = get_object_or_404(GoogleSyncTask, id=task_id)

        return JsonResponse({
            'success': True,
            'status': task.status,
            'progress': task.get_progress_percentage(),
            'processed_rows': task.processed_rows,
            'total_rows': task.total_rows,
            'successful_rows': task.successful_rows,
            'failed_rows': task.failed_rows,
            'error_message': task.error_message,
            'results': task.results
        })

    except Exception as e:
        logger.error(f"خطأ في جلب حالة المهمة: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
