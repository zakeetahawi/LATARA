from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .models import Customer, CustomerCategory, CustomerNote
from accounts.models import Branch

class CustomerForm(forms.ModelForm):
    phone2 = forms.CharField(
        label=_('رقم الهاتف الثاني'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'dir': 'ltr',
            'placeholder': _('أدخل رقم الهاتف الثاني (اختياري)')
        })
    )

    class Meta:
        model = Customer
        fields = [
            'name', 'phone', 'phone2', 'email', 'address',
            'customer_type', 'category', 'status', 'interests',
            'notes', 'image'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'dir': 'ltr'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'dir': 'ltr'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'customer_type': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'interests': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user and hasattr(user, 'branch') and user.branch:
            if user.branch.is_main_branch:
                # If user is from main branch, add branch field
                Branch = type(user.branch)
                self.fields['branch'] = forms.ModelChoiceField(
                    queryset=Branch.objects.filter(is_active=True),
                    label=_('الفرع'),
                    required=True,
                    empty_label=_('اختر الفرع'),
                    widget=forms.Select(attrs={
                        'class': 'form-select',
                        'required': 'required'
                    })
                )
                if 'branch' not in self._meta.fields:
                    self._meta.fields.append('branch')
            else:
                # If user is not from main branch, their branch will be set in the view
                self.fields.pop('branch', None)

        # Update customer type choices dynamically
        customer_types = Customer.get_customer_types()
        if not customer_types:
            from .models import CustomerType
            types = [(t.code, t.name) 
                    for t in CustomerType.objects.filter(is_active=True).order_by('name')]
            self.fields['customer_type'].choices = types
        else:
            self.fields['customer_type'].choices = customer_types

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            # Check file size (limit to 5MB)
            if image.size > 5 * 1024 * 1024:
                raise ValidationError(_('حجم الصورة يجب أن لا يتجاوز 5 ميجابايت'))
            
            # Check file extension
            allowed_extensions = ['jpg', 'jpeg', 'png']
            ext = image.name.split('.')[-1].lower()
            if ext not in allowed_extensions:
                raise ValidationError(_('يجب أن تكون الصورة بصيغة JPG أو PNG'))
            
        return image

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            qs = Customer.objects.filter(phone=phone)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                existing = qs.first()
                raise ValidationError(
                    _('رقم الهاتف مستخدم بالفعل للعميل: %(name)s (الفرع: %(branch)s)\nيمكنك إنشاء الطلب مباشرة باسم العميل الموجود.'),
                    code='duplicate_phone',
                    params={'name': existing.name, 'branch': existing.branch.name if existing.branch else '-'}
                )
        return phone

class CustomerNoteForm(forms.ModelForm):
    class Meta:
        model = CustomerNote
        fields = ['note']
        widgets = {
            'note': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('أضف ملاحظتك هنا...')
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        note = super().save(commit=False)
        if self.user:
            note.created_by = self.user
        if commit:
            note.save()
        return note

class CustomerSearchForm(forms.Form):
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('بحث عن عميل...')
        })
    )
    category = forms.ModelChoiceField(
        queryset=CustomerCategory.objects.all(),
        required=False,
        empty_label=_('كل التصنيفات'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.filter(is_active=True),
        required=False,
        empty_label=_('كل الفروع'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    customer_type = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    status = forms.ChoiceField(
        choices=[('', _('كل الحالات'))] + list(Customer.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Update customer type choices dynamically
        self.fields['customer_type'].choices = (
            [('', _('كل الأنواع'))] + list(Customer.get_customer_types())
        )
