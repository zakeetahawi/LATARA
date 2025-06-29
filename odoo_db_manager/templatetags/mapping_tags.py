from django import template

register = template.Library()

@register.filter
def get_mapping_value(column_mappings, column_name):
    """إرجاع قيمة التعيين للعمود المحدد"""
    if isinstance(column_mappings, dict):
        return column_mappings.get(column_name, '')
    return ''

@register.simple_tag
def is_column_mapped(column_mappings, column_name, field_type):
    """فحص ما إذا كان العمود معين لنوع الحقل المحدد"""
    if isinstance(column_mappings, dict):
        return column_mappings.get(column_name) == field_type
    return False
