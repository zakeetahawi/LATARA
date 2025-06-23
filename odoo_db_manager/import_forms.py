"""
النماذج المحسنة لاستيراد البيانات من Google Sheets
"""
from django import forms
from django.utils.translation import gettext_lazy as _


class GoogleSheetsImportForm(forms.Form):
    """نموذج مبسط لاستيراد البيانات من Google Sheets"""
    
    # معرف جدول البيانات (اختياري - سيتم جلبه من الإعدادات)
    spreadsheet_id = forms.CharField(
        label=_('معرف جدول البيانات (اختياري)'),
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'مثال: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
        }),
        help_text=_('اتركه فارغاً لاستخدام الجدول المحدد في الإعدادات')
    )
    
    # اسم الصفحة (سيتم تحديثها ديناميكياً)
    sheet_name = forms.ChoiceField(
        label=_('اختر الصفحة'),
        choices=[],
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'sheet_name_select'
        }),
        help_text=_('اختر الصفحة التي تريد استيراد البيانات منها')
    )
    
    # خيار استيراد جميع البيانات
    import_all = forms.BooleanField(
        label=_('استيراد جميع البيانات'),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'import_all_checkbox',
            'onchange': 'toggleRangeFields()'
        }),
        help_text=_('تحديد هذا الخيار سيستورد جميع البيانات من الصفحة')
    )
    
    # نطاق الصفوف (يظهر فقط عند عدم تحديد استيراد جميع البيانات)
    start_row = forms.IntegerField(
        label=_('من الصف'),
        min_value=2,  # بدء من الصف الثاني (بعد العناوين)
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '2',
            'id': 'start_row_input'
        }),
        help_text=_('رقم الصف الأول للبدء منه (الصف الأول مخصص للعناوين)')
    )
    
    end_row = forms.IntegerField(
        label=_('إلى الصف'),
        min_value=2,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '100',
            'id': 'end_row_input'
        }),
        help_text=_('رقم الصف الأخير للاستيراد حتى')
    )
    
    # خيار حذف البيانات الموجودة
    clear_existing = forms.BooleanField(
        label=_('حذف البيانات الموجودة'),
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'clear_existing_checkbox'
        }),
        help_text=_(
            'تحذير: سيتم حذف جميع البيانات الموجودة من نفس النوع قبل الاستيراد'
        )
    )
    
    def __init__(self, *args, **kwargs):
        # جلب قائمة الصفحات المتاحة
        available_sheets = kwargs.pop('available_sheets', [])
        super().__init__(*args, **kwargs)
        
        # تحديث خيارات الصفحات
        sheet_choices = [('', _('-- اختر صفحة --'))]
        for sheet in available_sheets:
            # إذا كان sheet dict فيه title
            if isinstance(sheet, dict) and 'title' in sheet:
                sheet_choices.append((
                    sheet['title'],
                    f"{sheet['title']} ({sheet.get('row_count', 0)} صف)"
                ))
            # إذا كان sheet نص فقط
            elif isinstance(sheet, str):
                sheet_choices.append((sheet, sheet))
            # إذا كان tuple (العنوان، العنوان)
            elif isinstance(sheet, tuple) and len(sheet) == 2:
                sheet_choices.append(sheet)
            else:
                # أي نوع آخر: حوله لنص
                sheet_choices.append((str(sheet), str(sheet)))
        
        self.fields['sheet_name'].choices = sheet_choices
    
    def clean(self):
        cleaned_data = super().clean()
        import_all = cleaned_data.get('import_all')
        start_row = cleaned_data.get('start_row')
        end_row = cleaned_data.get('end_row')
        
        # التحقق من صحة النطاق إذا لم يتم تحديد استيراد جميع البيانات
        if not import_all:
            if not start_row:
                raise forms.ValidationError(
                    _('يجب تحديد رقم الصف الأول عند عدم اختيار استيراد جميع البيانات')
                )
            if not end_row:
                raise forms.ValidationError(
                    _('يجب تحديد رقم الصف الأخير عند عدم اختيار استيراد جميع البيانات')
                )
            if start_row >= end_row:
                raise forms.ValidationError(
                    _('يجب أن يكون رقم الصف الأول أقل من رقم الصف الأخير')
                )
        
        return cleaned_data


class SheetSelectionForm(forms.Form):
    """نموذج اختيار الصفحة فقط للعمليات السريعة"""
    
    spreadsheet_url = forms.URLField(
        label=_('رابط جدول البيانات'),
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://docs.google.com/spreadsheets/d/...',
            'onchange': 'extractSpreadsheetId(this.value)'
        }),
        help_text=_('يمكنك لصق رابط جدول البيانات مباشرة')
    )
    
    spreadsheet_id = forms.CharField(
        label=_('معرف جدول البيانات'),
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'spreadsheet_id_input',
            'placeholder': '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        spreadsheet_url = cleaned_data.get('spreadsheet_url')
        spreadsheet_id = cleaned_data.get('spreadsheet_id')
        
        # إذا تم إدخال رابط، استخراج المعرف منه
        if spreadsheet_url and not spreadsheet_id:
            import re
            match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', spreadsheet_url)
            if match:
                cleaned_data['spreadsheet_id'] = match.group(1)
            else:
                raise forms.ValidationError(
                    _('رابط جدول البيانات غير صحيح')
                )
        
        return cleaned_data
