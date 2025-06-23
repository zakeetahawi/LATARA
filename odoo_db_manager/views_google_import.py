"""
العروض المحسنة لاستيراد البيانات من Google Sheets
"""
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .import_forms import GoogleSheetsImportForm
from .google_sheets_import import GoogleSheetsImporter
from .models import ImportLog

logger = logging.getLogger(__name__)


def is_staff_or_superuser(user):
    """التحقق من أن المستخدم موظف أو مشرف"""
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(is_staff_or_superuser)
def google_sheets_import_dashboard(request):
    """الصفحة الرئيسية لاستيراد البيانات من Google Sheets"""

    context = {
        'title': 'استيراد البيانات من Google Sheets',
        'recent_imports': ImportLog.objects.filter(
            user=request.user
        ).order_by('-created_at')[:5]
    }

    return render(
        request,
        'odoo_db_manager/google_import_dashboard.html',
        context
    )


@login_required
@user_passes_test(is_staff_or_superuser)
def google_sheets_import_form(request):
    """نموذج استيراد البيانات من Google Sheets"""

    if request.method == 'POST':
        return handle_import_form_submission(request)

    # إعداد النموذج
    try:
        importer = GoogleSheetsImporter()
        importer.initialize()
        available_sheets = importer.get_available_sheets()
        # حماية إضافية: إذا كانت available_sheets نص أو None، حولها لقائمة فارغة
        if not isinstance(available_sheets, list):
            logger.error(f"available_sheets ليس قائمة: {available_sheets!r}")
            available_sheets = []
        # إذا كانت العناصر ليست نصوصًا، استخرج العناوين فقط
        if available_sheets and not all(isinstance(s, str) for s in available_sheets):
            try:
                available_sheets = [
                    s['title'] if isinstance(s, dict) and 'title' in s else str(s)
                    for s in available_sheets
                ]
            except Exception as e:
                logger.error(f"فشل في تحويل available_sheets إلى قائمة عناوين: {e}")
                available_sheets = []
        # لا تحولها إلى قائمة tuples هنا، فقط قائمة نصوص
        form = GoogleSheetsImportForm(available_sheets=available_sheets)

        context = {
            'title': 'استيراد البيانات من Google Sheets',
            'form': form,
            'available_sheets': available_sheets,
            'has_config': True
        }

    except Exception as e:
        logger.error(f"خطأ في تحميل نموذج الاستيراد: {str(e)}")
        messages.error(request, f'خطأ في الإعداد: {str(e)}')

        context = {
            'title': 'استيراد البيانات من Google Sheets',
            'form': None,
            'available_sheets': [],
            'has_config': False,
            'error_message': str(e)
        }

    return render(request, 'odoo_db_manager/google_import_form.html', context)


def handle_import_form_submission(request):
    """معالجة إرسال النموذج"""
    try:
        importer = GoogleSheetsImporter()
        importer.initialize()
        available_sheets = importer.get_available_sheets()

        form = GoogleSheetsImportForm(
            request.POST,
            available_sheets=available_sheets
        )

        if form.is_valid():
            # حفظ بيانات النموذج في الجلسة للخطوة التالية
            request.session['import_data'] = {
                'sheet_name': form.cleaned_data['sheet_name'],
                'import_all': form.cleaned_data['import_all'],
                'start_row': form.cleaned_data.get('start_row'),
                'end_row': form.cleaned_data.get('end_row'),
                'clear_existing': form.cleaned_data['clear_existing'],
                'spreadsheet_id': form.cleaned_data.get('spreadsheet_id')
            }

            # إعادة التوجيه إلى صفحة المعاينة
            return redirect('odoo_db_manager:google_import_preview')

        else:
            # إرجاع النموذج مع الأخطاء
            context = {
                'title': 'استيراد البيانات من Google Sheets',
                'form': form,
                'available_sheets': available_sheets,
                'has_config': True
            }
            return render(
                request,
                'odoo_db_manager/google_import_form.html',
                context
            )

    except Exception as e:
        logger.error(f"خطأ في معالجة النموذج: {str(e)}")
        messages.error(request, f'خطأ في معالجة النموذج: {str(e)}')
        return redirect('odoo_db_manager:google_import_form')


@login_required
@user_passes_test(is_staff_or_superuser)
def google_sheets_import_preview(request):
    """معاينة البيانات قبل الاستيراد"""

    # التحقق من وجود بيانات في الجلسة
    if 'import_data' not in request.session:
        messages.error(
            request,
            'لا توجد بيانات للمعاينة. يرجى البدء من جديد.'
        )
        return redirect('odoo_db_manager:google_import_form')

    import_data = request.session['import_data']

    try:
        importer = GoogleSheetsImporter()
        importer.initialize()

        # معاينة البيانات
        preview = importer.preview_data(import_data['sheet_name'])

        context = {
            'title': 'معاينة البيانات للاستيراد',
            'sheet_name': import_data['sheet_name'],
            'headers': preview['headers'],
            'preview_data': preview['data'],
            'total_rows': preview['total_rows'],
            'import_settings': import_data,
            'max_preview_rows': 10
        }

        return render(
            request,
            'odoo_db_manager/google_import_preview.html',
            context
        )

    except Exception as e:
        logger.error(f"خطأ في معاينة البيانات: {str(e)}")
        messages.error(request, f'خطأ في معاينة البيانات: {str(e)}')
        return redirect('odoo_db_manager:google_import_form')


@login_required
@user_passes_test(is_staff_or_superuser)
@require_http_methods(["POST"])
def google_sheets_import_execute(request):
    """تنفيذ عملية الاستيراد"""

    # التحقق من وجود بيانات في الجلسة
    if 'import_data' not in request.session:
        messages.error(
            request,
            'لا توجد بيانات للاستيراد. يرجى البدء من جديد.'
        )
        return redirect('odoo_db_manager:google_import_form')

    import_data = request.session['import_data']

    try:
        importer = GoogleSheetsImporter()
        importer.initialize()

        # جلب البيانات
        if import_data['import_all']:
            data = importer.get_sheet_data(import_data['sheet_name'])
        else:
            data = importer.get_sheet_data(
                import_data['sheet_name'],
                import_all=False,
                start_row=import_data['start_row'],
                end_row=import_data['end_row']
            )

        if not data:
            messages.warning(request, 'لا توجد بيانات للاستيراد.')
            return redirect('odoo_db_manager:google_import_preview')

        # تنفيذ الاستيراد
        result = importer.import_data_by_type(
            import_data['sheet_name'],
            data,
            import_data.get('clear_existing', False),
            getattr(request, 'user', None)
        )

        # إنشاء سجل الاستيراد
        import_log = ImportLog.objects.create(
            user=request.user,
            created_by=getattr(request, 'user', None),
            sheet_name=import_data['sheet_name'],
            total_records=len(data),
            imported_records=result.get('imported', 0),
            updated_records=result.get('updated', 0),
            failed_records=result.get('failed', 0),
            clear_existing=import_data.get('clear_existing', False),
            status='success' if result.get('failed', 0) == 0 else 'partial',
            error_details='\n'.join(result.get('errors', []))
            if result.get('errors') else ''
        )

        # حذف بيانات الجلسة
        del request.session['import_data']

        # إعداد رسائل النجاح
        success_msg = f"تم استيراد {result['imported']} سجل جديد"
        if result['updated'] > 0:
            success_msg += f" وتحديث {result['updated']} سجل"

        messages.success(request, success_msg)

        if result['failed'] > 0:
            messages.warning(
                request,
                f"فشل في استيراد {result['failed']} سجل. "
                "راجع تفاصيل الأخطاء في سجل الاستيراد."
            )

        # إعادة التوجيه إلى صفحة النتائج
        return redirect(
            'odoo_db_manager:google_import_result',
            import_id=import_log.pk
        )

    except Exception as e:
        logger.error(f"خطأ في تنفيذ الاستيراد: {str(e)}")
        messages.error(request, f'خطأ في تنفيذ الاستيراد: {str(e)}')
        return redirect('odoo_db_manager:google_import_preview')


@login_required
@user_passes_test(is_staff_or_superuser)
def google_sheets_import_result(request, import_id):
    """عرض نتائج الاستيراد"""

    try:
        import_log = ImportLog.objects.get(id=import_id, user=request.user)

        context = {
            'title': 'نتائج الاستيراد',
            'import_log': import_log,
            'success_percentage': round(
                (import_log.imported_records + import_log.updated_records) /
                import_log.total_records * 100, 1
            ) if import_log.total_records > 0 else 0
        }

        return render(
            request,
            'odoo_db_manager/google_import_result.html',
            context
        )

    except ImportLog.DoesNotExist:
        messages.error(request, 'سجل الاستيراد غير موجود.')
        return redirect('odoo_db_manager:google_import_dashboard')


@login_required
@user_passes_test(is_staff_or_superuser)
def import_logs(request):
    """عرض سجل عمليات الاستيراد"""
    
    logs = ImportLog.objects.filter(
        user=request.user
    ).order_by('-created_at')
    
    context = {
        'title': 'سجل عمليات الاستيراد',
        'logs': logs
    }
    
    return render(
        request,
        'odoo_db_manager/import_logs.html',
        context
    )


@login_required
@user_passes_test(is_staff_or_superuser)
def get_sheets_ajax(request):
    """API لجلب قائمة الصفحات عبر AJAX"""

    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    spreadsheet_id = request.GET.get('spreadsheet_id')
    original_id = None

    try:
        importer = GoogleSheetsImporter()

        # استخدام معرف مخصص إذا تم توفيره
        if spreadsheet_id:
            # تحديث الإعداد مؤقتاً
            original_id = (importer.config.spreadsheet_id
                           if importer.config else None)
            if importer.config:
                importer.config.spreadsheet_id = spreadsheet_id

        importer.initialize()
        sheets = importer.get_available_sheets()

        # استعادة المعرف الأصلي
        if spreadsheet_id and importer.config and original_id:
            importer.config.spreadsheet_id = original_id

        return JsonResponse({
            'success': True,
            'sheets': sheets
        })

    except Exception as e:
        logger.error(f"خطأ في جلب قائمة الصفحات: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@user_passes_test(is_staff_or_superuser)
@require_http_methods(["POST"])
def google_import_all(request):
    """استيراد شامل لكل الصفحات المدعومة من جدول Google Sheets"""
    try:
        importer = GoogleSheetsImporter()
        importer.initialize()
        all_sheets = importer.get_available_sheets()
        # قائمة الصفحات المدعومة فقط (حسب model_map)
        supported_keys = [
            'customers', 'عملاء', 'orders', 'طلبات', 'products', 'منتجات',
            'users', 'مستخدمين', 'branches', 'فروع', 'databases', 'قواعد البيانات',
            'inspections', 'معاينات', 'settings', 'إعدادات الشركة والنظام'
        ]
        imported_logs = []
        for sheet in all_sheets:
            if any(key in sheet.lower() for key in supported_keys):
                data = importer.get_sheet_data(sheet)
                result = importer.import_data_by_type(sheet, data, clear_existing=False, user=request.user)
                import_log = ImportLog.objects.create(
                    user=request.user,
                    created_by=getattr(request, 'user', None),
                    sheet_name=sheet,
                    total_records=len(data),
                    imported_records=result.get('imported', 0),
                    updated_records=result.get('updated', 0),
                    failed_records=result.get('failed', 0),
                    clear_existing=False,
                    status='success' if result.get('failed', 0) == 0 else 'partial',
                    error_details='\n'.join(result.get('errors', [])) if result.get('errors') else ''
                )
                imported_logs.append(import_log)
        messages.success(request, f"تم استيراد جميع الصفحات المدعومة ({len(imported_logs)}) بنجاح.")
        return redirect('odoo_db_manager:import_logs')
    except Exception as e:
        logger.error(f"خطأ في الاستيراد الشامل: {str(e)}")
        messages.error(request, f'خطأ في الاستيراد الشامل: {str(e)}')
        return redirect('odoo_db_manager:google_import_dashboard')
