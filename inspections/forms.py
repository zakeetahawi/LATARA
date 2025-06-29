from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from accounts.models import Branch, User
from .models import (
    Inspection,
    InspectionEvaluation,
    InspectionReport,
    InspectionNotification
)

class InspectionEvaluationForm(forms.Form):
    # عرض جميع معايير التقييم دفعة واحدة
    CRITERIA_CHOICES = [
        ('location', _('الموقع')),
        ('condition', _('الحالة')),
        ('suitability', _('الملاءمة')),
        ('safety', _('السلامة')),
        ('accessibility', _('سهولة الوصول')),
    ]
    RATING_CHOICES = [
        (1, _('ضعيف')),
        (2, _('مقبول')),
        (3, _('جيد')),
        (4, _('جيد جداً')),
        (5, _('ممتاز')),
    ]
    notes = forms.CharField(label=_('ملاحظات التقييم'), required=False, widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}))
    # إضافة حقل تقييم لكل معيار
    location = forms.ChoiceField(label=_('الموقع'), choices=RATING_CHOICES, widget=forms.RadioSelect)
    condition = forms.ChoiceField(label=_('الحالة'), choices=RATING_CHOICES, widget=forms.RadioSelect)
    suitability = forms.ChoiceField(label=_('الملاءمة'), choices=RATING_CHOICES, widget=forms.RadioSelect)
    safety = forms.ChoiceField(label=_('السلامة'), choices=RATING_CHOICES, widget=forms.RadioSelect)
    accessibility = forms.ChoiceField(label=_('سهولة الوصول'), choices=RATING_CHOICES, widget=forms.RadioSelect)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field != 'notes':
                self.fields[field].widget.attrs.update({'class': 'form-check-input'})

class InspectionReportForm(forms.ModelForm):
    class Meta:
        model = InspectionReport
        fields = ['title', 'report_type', 'branch', 'date_from', 'date_to', 'notes']
        widgets = {
            'date_from': forms.DateInput(attrs={'type': 'date'}),
            'date_to': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class': 'form-control'
            })

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')

        if date_from and date_to and date_to < date_from:
            raise ValidationError(_('تاريخ النهاية يجب أن يكون بعد تاريخ البداية'))

        return cleaned_data

class InspectionNotificationForm(forms.ModelForm):
    class Meta:
        model = InspectionNotification
        fields = ['type', 'message', 'scheduled_for']
        widgets = {
            'scheduled_for': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
            'message': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class': 'form-control'
            })

    def clean_scheduled_for(self):
        scheduled_for = self.cleaned_data.get('scheduled_for')
        if scheduled_for and scheduled_for < timezone.now():
            raise ValidationError(_('لا يمكن تحديد موعد في الماضي'))
        return scheduled_for

class InspectionFilterForm(forms.Form):
    search = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': _('بحث...')
    }))
    status = forms.ChoiceField(
        choices=[('', _('كل الحالات'))] + Inspection.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        required=False,
        empty_label=_('كل الفروع'),
        widget=forms.Select(attrs={'class': 'form-control'})
    )

class InspectionForm(forms.ModelForm):
    responsible_employee = forms.ModelChoiceField(
        queryset=None,
        label=_('البائع'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control select2'})
    )

    class Meta:
        model = Inspection
        fields = [
            'customer', 'contract_number', 'inspector', 'request_date',
            'scheduled_date', 'windows_count', 'notes', 'inspection_file',
            'branch', 'responsible_employee', 'status', 'result'
        ]
        widgets = {
            'request_date': forms.DateInput(attrs={'type': 'date'}),
            'scheduled_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
            'inspection_file': forms.FileInput(attrs={'accept': '.pdf'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'result': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, user=None, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set inspector queryset
        self.fields['inspector'].queryset = User.objects.filter(
            is_active=True,
            is_inspection_technician=True
        )
        
        # Set responsible employee (salesperson) queryset
        from accounts.models import Salesperson
        self.fields['responsible_employee'].queryset = Salesperson.objects.filter(is_active=True)
        
        # Set branch if user is not superuser
        if user and not user.is_superuser:
            self.fields['branch'].initial = user.branch
            self.fields['branch'].widget.attrs['readonly'] = True
            self.fields['branch'].disabled = True
            
        # قفل تاريخ الطلب عند التعديل والحفاظ على قيمته
        if self.instance.pk:  # في حالة تعديل معاينة موجودة
            self.fields['request_date'].disabled = True
            self.fields['request_date'].widget.attrs['readonly'] = True
            self.initial['request_date'] = self.instance.request_date
        else:  # في حالة إنشاء معاينة جديدة
            today = timezone.now().date()
            self.fields['request_date'].initial = today
            self.initial['request_date'] = today
            
        # إعداد تسميات وخصائص حقول الحالة والنتيجة
        self.fields['status'].label = _('حالة المعاينة')
        self.fields['result'].label = _('نتيجة المعاينة')
        self.fields['status'].widget.attrs.update({'class': 'form-control'})
        self.fields['result'].widget.attrs.update({'class': 'form-control'})
        self.fields['result'].required = False  # جعل حقل النتيجة غير إلزامي بشكل مبدئي

        # سيناريو 1: إذا كان هناك طلب مرتبط جديد، قم بتعيين البائع تلقائياً
        if order and order.salesperson:
            self.initial['responsible_employee'] = order.salesperson.id
            self.fields['responsible_employee'].initial = order.salesperson.id
            self.fields['responsible_employee'].disabled = True
            self.fields['responsible_employee'].widget.attrs['readonly'] = True
            self.fields['responsible_employee'].help_text = _('تم تعيين البائع تلقائياً من الطلب المرتبط')
        
        # سيناريو 2: إذا كانت المعاينة مرتبطة بطلب وتم حفظها
        elif self.instance.pk and hasattr(self.instance, 'order') and self.instance.order and self.instance.order.salesperson:
            # تعيين البائع الحالي من الطلب المرتبط
            self.initial['responsible_employee'] = self.instance.order.salesperson.id
            self.fields['responsible_employee'].initial = self.instance.order.salesperson.id
            
            # إذا لم يكن البائع معيناً بعد في المعاينة، استخدام بائع الطلب
            if not self.instance.responsible_employee:
                self.instance.responsible_employee = self.instance.order.salesperson
            
            self.fields['responsible_employee'].disabled = True
            self.fields['responsible_employee'].widget.attrs['readonly'] = True
            self.fields['responsible_employee'].help_text = _('تم تعيين البائع تلقائياً من الطلب المرتبط')
        
        # سيناريو 3: إذا كان البائع موجود بالفعل في المعاينة وهي من طلب
        elif self.instance.pk and self.instance.is_from_orders:
            # تأكد من إظهار قيمة البائع الحالية
            if self.instance.responsible_employee:
                self.initial['responsible_employee'] = self.instance.responsible_employee.id
                self.fields['responsible_employee'].initial = self.instance.responsible_employee.id
            
            # إذا كان هناك طلب مرتبط لكن لم يتم تعيين البائع، حاول تعيينه من الطلب
            elif hasattr(self.instance, 'order') and self.instance.order and self.instance.order.salesperson:
                self.initial['responsible_employee'] = self.instance.order.salesperson.id
                self.fields['responsible_employee'].initial = self.instance.order.salesperson.id
                self.instance.responsible_employee = self.instance.order.salesperson
            
            self.fields['responsible_employee'].disabled = True
            self.fields['responsible_employee'].widget.attrs['readonly'] = True
            self.fields['responsible_employee'].help_text = _('لا يمكن تغيير البائع بعد إنشاء المعاينة من طلب')

        # Make fields optional as needed
        self.fields['notes'].required = False
        self.fields['customer'].required = False
        self.fields['contract_number'].required = False
        self.fields['inspector'].required = True

        # Custom labels
        self.fields['contract_number'].label = _('رقم العقد')
        self.fields['customer'].label = _('العميل')
        self.fields['inspector'].label = _('المعاين')
        self.fields['branch'].label = _('الفرع')
        self.fields['request_date'].label = _('تاريخ الطلب')
        self.fields['scheduled_date'].label = _('تاريخ التنفيذ')
        self.fields['windows_count'].label = _('عدد الشبابيك')
        self.fields['inspection_file'].label = _('ملف المعاينة')
        self.fields['notes'].label = _('ملاحظات')

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        result = cleaned_data.get('result')
        scheduled_date = cleaned_data.get('scheduled_date')
        request_date = cleaned_data.get('request_date')

        # إذا كانت الحالة مكتملة، يجب تحديد النتيجة
        if status == 'completed' and not result:
            self.add_error('result', _('يجب تحديد النتيجة عند اكتمال المعاينة'))

        # تاريخ التنفيذ يجب أن يكون بعد أو يساوي تاريخ الطلب
        if request_date and scheduled_date and scheduled_date < request_date:
            self.add_error('scheduled_date', _('تاريخ التنفيذ يجب أن يكون بعد أو يساوي تاريخ الطلب'))

        # تاريخ التنفيذ إلزامي
        if not scheduled_date:
            self.add_error('scheduled_date', _('يجب تحديد تاريخ التنفيذ'))

        return cleaned_data

class InspectionSearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('بحث بكود العميل أو اسم العميل أو رقم الطلب أو رقم العقد أو رقم الهاتف...')
        })
    )
    branch = forms.CharField(required=False)
    status = forms.CharField(required=False)
    from_orders = forms.CharField(required=False)
    is_duplicated = forms.CharField(required=False)
