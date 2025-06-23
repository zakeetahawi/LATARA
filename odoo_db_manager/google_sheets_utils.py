"""
أدوات مساعدة للتعامل مع Google Sheets
Google Sheets Utilities
"""

import logging
import urllib.parse
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def encode_sheet_name(sheet_name: str) -> str:
    """
    تشفير اسم الصفحة للتعامل مع الأسماء العربية
    Encode sheet name to handle Arabic names
    """
    return urllib.parse.quote(sheet_name, safe='')


def build_range_name(sheet_name: str, start_row: Optional[int] = None,
                    end_row: Optional[int] = None, start_col: str = 'A',
                    end_col: str = 'Z') -> str:
    """
    بناء اسم النطاق لـ Google Sheets
    Build range name for Google Sheets
    """
    # تنظيف اسم الصفحة
    clean_sheet_name = sheet_name.strip()

    # إزالة علامات الاقتباس الموجودة مسبقاً
    if clean_sheet_name.startswith("'") and clean_sheet_name.endswith("'"):
        clean_sheet_name = clean_sheet_name[1:-1]

    # إذا كان الاسم يحتوي على مسافات أو أحرف خاصة، ضعه بين علامتي اقتباس
    needs_quotes = (
        ' ' in clean_sheet_name or
        any(char in clean_sheet_name for char in ['!', "'", '"', '-', '(', ')', '[', ']']) or
        is_arabic_text(clean_sheet_name)
    )

    if needs_quotes:
        # استخدام علامات اقتباس مفردة وتجنب التداخل
        clean_sheet_name = f"'{clean_sheet_name.replace("'", "''")}'"

    # بناء النطاق
    if start_row is None and end_row is None:
        # جلب كامل الصفحة
        return clean_sheet_name
    elif start_row is not None and end_row is not None:
        # نطاق محدد
        return f"{clean_sheet_name}!{start_col}{start_row}:{end_col}{end_row}"
    elif start_row is not None:
        # من صف معين إلى النهاية
        return f"{clean_sheet_name}!{start_col}{start_row}:{end_col}"
    else:
        # من البداية إلى صف معين
        return f"{clean_sheet_name}!{start_col}1:{end_col}{end_row}"


def find_sheet_by_name(service, spreadsheet_id: str, sheet_name: str) -> Optional[Dict[str, Any]]:
    """
    البحث عن صفحة بالاسم وإرجاع معلوماتها
    Find sheet by name and return its info
    """
    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()

        for sheet in spreadsheet.get('sheets', []):
            sheet_properties = sheet.get('properties', {})
            sheet_title = sheet_properties.get('title', '')

            if sheet_title == sheet_name:
                return {
                    'id': sheet_properties.get('sheetId'),
                    'title': sheet_title,
                    'index': sheet_properties.get('index', 0),
                    'properties': sheet_properties
                }

        return None

    except Exception as e:
        logger.error(f"خطأ في البحث عن الصفحة {sheet_name}: {str(e)}")
        return None


def get_sheet_data_safe(service, spreadsheet_id: str, sheet_name: str,
                       start_row: Optional[int] = None, end_row: Optional[int] = None) -> List[List[str]]:
    """
    جلب بيانات الصفحة مع معالجة آمنة للأسماء العربية
    Get sheet data with safe handling of Arabic names
    """
    try:
        # محاولة 1: استخدام الاسم مباشرة
        range_name = build_range_name(sheet_name, start_row, end_row)

        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()

            return result.get('values', [])

        except Exception as first_error:
            logger.warning(f"فشل في المحاولة الأولى لجلب البيانات: {str(first_error)}")

            # محاولة 2: البحث عن الصفحة والحصول على معلوماتها
            sheet_info = find_sheet_by_name(service, spreadsheet_id, sheet_name)

            if not sheet_info:
                raise Exception(f"لم يتم العثور على الصفحة '{sheet_name}'")

            # محاولة 3: استخدام اسم الصفحة مع علامات اقتباس
            quoted_range = build_range_name(f"'{sheet_name}'", start_row, end_row)

            try:
                result = service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=quoted_range
                ).execute()

                return result.get('values', [])

            except Exception as second_error:
                logger.warning(f"فشل في المحاولة الثانية: {str(second_error)}")

                # محاولة 4: استخدام فهرس الصفحة
                sheet_index = sheet_info['index']
                index_range = f"Sheet{sheet_index + 1}"

                if start_row is not None or end_row is not None:
                    start_col = 'A'
                    end_col = 'Z'
                    start_r = start_row or 1
                    end_r = end_row or 1000
                    index_range = f"{index_range}!{start_col}{start_r}:{end_col}{end_r}"

                try:
                    result = service.spreadsheets().values().get(
                        spreadsheetId=spreadsheet_id,
                        range=index_range
                    ).execute()

                    return result.get('values', [])

                except Exception as third_error:
                    logger.error(f"فشل في جميع المحاولات: {str(third_error)}")
                    raise Exception(
                        f"فشل في جلب البيانات من الصفحة '{sheet_name}'. "
                        f"الأخطاء: {str(first_error)}, {str(second_error)}, {str(third_error)}"
                    )

    except Exception as e:
        logger.error(f"خطأ في جلب بيانات الصفحة {sheet_name}: {str(e)}")
        raise


def validate_sheet_access(service, spreadsheet_id: str) -> Dict[str, Any]:
    """
    التحقق من إمكانية الوصول إلى الجدول
    Validate access to spreadsheet
    """
    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()

        return {
            'success': True,
            'title': spreadsheet.get('properties', {}).get('title', 'Unknown'),
            'sheets': [
                sheet.get('properties', {}).get('title', '')
                for sheet in spreadsheet.get('sheets', [])
            ]
        }

    except Exception as e:
        error_msg = str(e).lower()

        if 'not found' in error_msg or '404' in error_msg:
            return {
                'success': False,
                'error': 'جدول البيانات غير موجود أو معرف الجدول غير صحيح.'
            }
        elif 'permission' in error_msg or '403' in error_msg:
            return {
                'success': False,
                'error': 'ليس لديك إذن للوصول إلى هذا الجدول. تأكد من مشاركته مع حساب الخدمة.'
            }
        else:
            return {
                'success': False,
                'error': f'خطأ في الاتصال مع Google Sheets: {str(e)}'
            }


def get_available_sheets(service, spreadsheet_id: str) -> List[str]:
    """
    جلب قائمة الصفحات المتاحة
    Get list of available sheets
    """
    try:
        validation = validate_sheet_access(service, spreadsheet_id)

        if validation['success']:
            return validation['sheets']
        else:
            raise Exception(validation['error'])

    except Exception as e:
        logger.error(f"فشل في جلب قائمة الصفحات: {str(e)}")
        raise


def normalize_sheet_name(sheet_name: str) -> str:
    """
    تطبيع اسم الصفحة
    Normalize sheet name
    """
    # إزالة المسافات الزائدة
    normalized = sheet_name.strip()

    # إزالة علامات الاقتباس إذا كانت موجودة
    if normalized.startswith("'") and normalized.endswith("'"):
        normalized = normalized[1:-1]

    return normalized


def is_arabic_text(text: str) -> bool:
    """
    التحقق من وجود نص عربي
    Check if text contains Arabic characters
    """
    arabic_range = range(0x0600, 0x06FF + 1)
    return any(ord(char) in arabic_range for char in text)


def safe_sheet_operation(service, spreadsheet_id: str, sheet_name: str, operation_func, *args, **kwargs):
    """
    تنفيذ عملية على الصفحة مع معالجة آمنة للأخطاء
    Execute sheet operation with safe error handling
    """
    try:
        # تطبيع اسم الصفحة
        normalized_name = normalize_sheet_name(sheet_name)

        # محاولة تنفيذ العملية
        return operation_func(service, spreadsheet_id, normalized_name, *args, **kwargs)

    except Exception as e:
        logger.error(f"خطأ في تنفيذ العملية على الصفحة {sheet_name}: {str(e)}")

        # إذا كان الاسم يحتوي على أحرف عربية، جرب طرق بديلة
        if is_arabic_text(sheet_name):
            logger.info(f"محاولة طرق بديلة للصفحة العربية: {sheet_name}")

            # جرب مع علامات اقتباس
            try:
                quoted_name = f"'{normalized_name}'"
                return operation_func(service, spreadsheet_id, quoted_name, *args, **kwargs)
            except Exception as quoted_error:
                logger.warning(f"فشل مع علامات الاقتباس: {str(quoted_error)}")

                # جرب باستخدام فهرس الصفحة
                try:
                    sheet_info = find_sheet_by_name(service, spreadsheet_id, normalized_name)
                    if sheet_info:
                        index_name = f"Sheet{sheet_info['index'] + 1}"
                        return operation_func(service, spreadsheet_id, index_name, *args, **kwargs)
                except Exception as index_error:
                    logger.error(f"فشل مع فهرس الصفحة: {str(index_error)}")

        # إذا فشلت جميع المحاولات، ارفع الخطأ الأصلي
        raise e
