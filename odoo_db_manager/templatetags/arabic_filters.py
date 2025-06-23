"""
فلاتر Django مخصصة للتعامل مع النصوص العربية
Custom Django filters for Arabic text handling
"""

from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
import html
import unicodedata

register = template.Library()


@register.filter
def fix_arabic_encoding(value):
    """
    إصلاح ترميز النص العربي
    Fix Arabic text encoding
    """
    if not value:
        return value
    
    try:
        # إذا كان النص مشفراً بـ HTML entities، فك التشفير
        if '&#' in str(value) or '&' in str(value):
            value = html.unescape(str(value))
        
        # تطبيع النص العربي
        value = unicodedata.normalize('NFKC', str(value))
        
        # إزالة الأحرف غير المرئية
        value = ''.join(char for char in value if unicodedata.category(char) != 'Cf')
        
        return value.strip()
        
    except Exception:
        return str(value)


@register.filter
def safe_arabic_text(value):
    """
    عرض النص العربي بشكل آمن
    Display Arabic text safely
    """
    if not value:
        return ""
    
    try:
        # إصلاح الترميز أولاً
        fixed_value = fix_arabic_encoding(value)
        
        # تنظيف HTML
        escaped_value = escape(fixed_value)
        
        # إضافة خصائص RTL
        return mark_safe(f'<span dir="rtl" class="arabic-text">{escaped_value}</span>')
        
    except Exception:
        return escape(str(value))


@register.filter
def is_arabic_text(value):
    """
    التحقق من وجود نص عربي
    Check if text contains Arabic characters
    """
    if not value:
        return False
    
    try:
        arabic_range = range(0x0600, 0x06FF + 1)
        return any(ord(char) in arabic_range for char in str(value))
    except Exception:
        return False


@register.filter
def clean_column_name(value):
    """
    تنظيف اسم العمود
    Clean column name
    """
    if not value:
        return ""
    
    try:
        # إصلاح الترميز
        cleaned = fix_arabic_encoding(value)
        
        # إزالة المسافات الزائدة
        cleaned = ' '.join(cleaned.split())
        
        # إزالة الأحرف الخاصة غير المرغوب فيها
        unwanted_chars = ['\u200c', '\u200d', '\u200e', '\u200f', '\ufeff']
        for char in unwanted_chars:
            cleaned = cleaned.replace(char, '')
        
        return cleaned.strip()
        
    except Exception:
        return str(value)


@register.filter
def format_field_type(value):
    """
    تنسيق نوع الحقل
    Format field type
    """
    if not value:
        return ""
    
    # قاموس ترجمة أنواع الحقول
    field_type_translations = {
        'customer_name': 'اسم العميل',
        'customer_phone': 'رقم الهاتف',
        'customer_email': 'البريد الإلكتروني',
        'customer_address': 'العنوان',
        'order_number': 'رقم الطلب',
        'invoice_number': 'رقم الفاتورة',
        'contract_number': 'رقم العقد',
        'total_amount': 'المبلغ الإجمالي',
        'paid_amount': 'المبلغ المدفوع',
        'order_status': 'حالة الطلب',
        'order_date': 'تاريخ الطلب',
        'delivery_date': 'تاريخ التسليم',
        'notes': 'ملاحظات',
        'salesperson': 'البائع',
        'branch': 'الفرع',
        'product_type': 'نوع المنتج',
        'quantity': 'الكمية',
        'unit_price': 'سعر الوحدة',
        'discount': 'الخصم',
        'tax': 'الضريبة',
        'ignore': 'تجاهل',
    }
    
    return field_type_translations.get(str(value), str(value))


@register.filter
def truncate_arabic(value, length=50):
    """
    اقتطاع النص العربي مع الحفاظ على التنسيق
    Truncate Arabic text while preserving formatting
    """
    if not value:
        return ""
    
    try:
        cleaned = clean_column_name(value)
        
        if len(cleaned) <= length:
            return cleaned
        
        # اقتطاع النص مع إضافة نقاط
        truncated = cleaned[:length-3] + "..."
        return truncated
        
    except Exception:
        return str(value)[:length]


@register.filter
def debug_encoding(value):
    """
    عرض معلومات الترميز للتشخيص
    Display encoding information for debugging
    """
    if not value:
        return "Empty value"
    
    try:
        info = []
        info.append(f"Type: {type(value).__name__}")
        info.append(f"Length: {len(str(value))}")
        info.append(f"Repr: {repr(value)}")
        
        # عرض أول 10 أحرف مع أكوادها
        chars_info = []
        for i, char in enumerate(str(value)[:10]):
            chars_info.append(f"{char}({ord(char)})")
        
        info.append(f"Chars: {', '.join(chars_info)}")
        
        return " | ".join(info)
        
    except Exception as e:
        return f"Error: {str(e)}"
