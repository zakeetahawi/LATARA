from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, ProtectedError
from django.core.paginator import Paginator
from django.core.paginator import Paginator
from django.db.models import Count, Case, When, IntegerField
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import Customer, CustomerCategory, CustomerNote
from orders.models import Order
from .forms import CustomerForm, CustomerSearchForm, CustomerNoteForm

def get_queryset_for_user(request):
    """دالة مساعدة للحصول على العملاء المسموح للمستخدم برؤيتهم"""
    if request.user.is_superuser:
        return Customer.objects.all()
    if request.user.branch:
        return Customer.objects.filter(branch=request.user.branch)
    return Customer.objects.none()

@login_required
def customer_list(request):
    """
    View for displaying the list of customers with search and filtering
    تم تحسين الأداء باستخدام select_related وتحسين الاستعلامات
    """
    form = CustomerSearchForm(request.GET)
    customers = get_queryset_for_user(request).select_related(
        'category', 'branch', 'created_by'
    ).prefetch_related('customer_orders')

    # تحسين الاستعلامات باستخدام الفهارس
    if form.is_valid():
        search = form.cleaned_data.get('search')
        category = form.cleaned_data.get('category')
        customer_type = form.cleaned_data.get('customer_type')
        status = form.cleaned_data.get('status')
        branch = form.cleaned_data.get('branch')

        # تحسين استعلام البحث
        if search:
            # استخدام استعلامات منفصلة لتحسين الأداء
            name_query = Q(name__icontains=search)
            code_query = Q(code__icontains=search)
            phone_query = Q(phone__icontains=search) | Q(phone2__icontains=search)
            email_query = Q(email__icontains=search)

            customers = customers.filter(
                name_query | code_query | phone_query | email_query
            )

        # استخدام الفهارس للتصفية
        if category:
            customers = customers.filter(category=category)

        if customer_type:
            customers = customers.filter(customer_type=customer_type)

        if status:
            customers = customers.filter(status=status)

        if branch:
            customers = customers.filter(branch=branch)

    # استخدام فهرس created_at للترتيب
    customers = customers.order_by('-created_at')

    # تحسين الأداء عن طريق حساب العدد الإجمالي مرة واحدة فقط
    total_customers = customers.count()

    # Pagination
    paginator = Paginator(customers, 10)  # Show 10 customers per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Store form values for template context
    search_value = request.GET.get('search', '')
    category_value = request.GET.get('category', '')
    customer_type_value = request.GET.get('customer_type', '')
    status_value = request.GET.get('status', '')

    branch_value = request.GET.get('branch', '')

    context = {
        'page_obj': page_obj,
        'form': form,
        'total_customers': total_customers,
        'search_query': search_value,
        'category_value': category_value,
        'customer_type_value': customer_type_value,
        'status_value': status_value,
        'branch_value': branch_value,
    }

    return render(request, 'customers/customer_list.html', context)

@login_required
def customer_detail(request, pk):
    """
    View for displaying customer details, orders, and notes
    تحسين الأداء باستخدام select_related و prefetch_related
    """
    customer = get_object_or_404(
        get_queryset_for_user(request).select_related(
            'category', 'branch', 'created_by'
        ),
        pk=pk
    )

    # تحسين استعلام الطلبات باستخدام prefetch_related
    customer_orders = customer.customer_orders.select_related('customer', 'salesperson', 'branch').prefetch_related('items').order_by('-created_at')[:5]

    # Get orders with items only (for product orders)
    orders = []
    for order in customer_orders:
        # Include service orders always
        if hasattr(order, 'order_type') and order.order_type == 'service':
            orders.append(order)
        # Include product orders only if they have items
        elif hasattr(order, 'order_type') and order.order_type == 'product' and order.items.exists():
            orders.append(order)
        # Include all orders if order_type is not available (new structure)
        elif not hasattr(order, 'order_type') or order.order_type is None:
            orders.append(order)

    # تحسين استعلام المعاينات باستخدام select_related
    inspections = customer.inspections.select_related('customer', 'branch', 'created_by').order_by('-created_at')[:5]

    # تحميل ملاحظات العميل مسبقًا
    customer_notes = customer.notes_history.select_related('created_by').order_by('-created_at')[:10]

    note_form = CustomerNoteForm()

    context = {
        'customer': customer,
        'orders': orders,
        'inspections': inspections,
        'note_form': note_form,
        'customer_notes': customer_notes,
    }

    return render(request, 'customers/customer_detail.html', context)

@login_required
@permission_required('customers.add_customer', raise_exception=True)
def customer_create(request):
    """
    View for creating a new customer with image upload
    """
    if not request.user.branch:
        messages.error(request, _('لا يمكنك إضافة عميل لأنك غير مرتبط بفرع'))
        return redirect('customers:customer_list')

    if request.method == 'POST':
        form = CustomerForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            try:
                customer = form.save(commit=False)
                customer.created_by = request.user

                # تعيين الفرع
                if request.user.branch.is_main_branch:
                    branch = form.cleaned_data.get('branch')
                    if not branch:
                        messages.error(request, _('يرجى اختيار الفرع'))
                        return render(request, 'customers/customer_form.html', {'form': form})
                    customer.branch = branch
                else:
                    customer.branch = request.user.branch

                customer.save()
                messages.success(request, _('تم إضافة العميل {} بنجاح').format(customer.name))
                return redirect('customers:customer_detail', pk=customer.pk)
            except Exception as e:
                messages.error(request, _('حدث خطأ أثناء حفظ العميل: {}').format(str(e)))
        else:
            print(f"Form errors: {form.errors}")  # للتشخيص
    else:
        form = CustomerForm(user=request.user)

    context = {
        'form': form,
        'title': _('إضافة عميل جديد')
    }
    return render(request, 'customers/customer_form.html', context)

@login_required
@permission_required('customers.change_customer', raise_exception=True)
def customer_update(request, pk):
    """
    View for updating customer details including image
    """
    try:
        customer = Customer.objects.select_related('branch').get(pk=pk)
    except Customer.DoesNotExist:
        messages.error(request, 'العميل غير موجود في قاعدة البيانات.')
        return redirect('customers:customer_list')

    # Check if user has access to this customer's branch
    if not request.user.is_superuser and customer.branch != request.user.branch:
        messages.error(request, 'لا يمكنك تعديل بيانات عميل في فرع آخر')
        return redirect('customers:customer_list')

    if request.method == 'POST':
        form = CustomerForm(request.POST, request.FILES, instance=customer, user=request.user)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'تم تحديث بيانات العميل بنجاح.')
                return redirect('customers:customer_detail', pk=customer.pk)
            except Exception as e:
                messages.error(request, f'حدث خطأ أثناء تحديث بيانات العميل: {str(e)}')
    else:
        form = CustomerForm(instance=customer, user=request.user)

    context = {
        'form': form,
        'customer': customer,
        'title': 'تعديل بيانات العميل'
    }

    return render(request, 'customers/customer_form.html', context)

@login_required
@permission_required('customers.delete_customer', raise_exception=True)
def customer_delete(request, pk):
    """View for deleting a customer with proper error handling."""
    customer = get_object_or_404(Customer, pk=pk)

    # Check related records before attempting deletion
    has_related_records = False
    relations = {
        'inspections': _('معاينة'),
        'orders': _('طلب'),
        'installations': _('تركيب'),
    }

    related_counts = {}
    for rel, label in relations.items():
        if hasattr(customer, rel):
            count = getattr(customer, rel).count()
            if count > 0:
                has_related_records = True
                related_counts[label] = count

    if request.method == 'POST':
        if has_related_records:
            # Format message showing all related records
            records_msg = ', '.join(
                f'{count} {label}'
                for label, count in related_counts.items()
            )
            msg = (
                f'لا يمكن حذف العميل لوجود السجلات التالية: {records_msg}. '
                'يمكنك تعطيل حساب العميل بدلاً من حذفه.'
            )
            messages.error(request, msg)
            return redirect('customers:customer_detail', pk=customer.pk)

        try:
            customer.delete()
            messages.success(request, 'تم حذف العميل بنجاح.')
            return redirect('customers:customer_list')
        except ProtectedError as e:
            # Determine related records from protection error
            protected_objects = list(e.protected_objects)
            relations_found = {
                'inspection': _('معاينات'),
                'order': _('طلبات'),
                'installation': _('تركيبات')
            }

            found_relations = [
                rel_name
                for model_name, rel_name in relations_found.items()
                if any(obj._meta.model_name == model_name
                      for obj in protected_objects)
            ]

            if found_relations:
                records_msg = ' و'.join(found_relations)
                msg = (
                    f'لا يمكن حذف العميل لوجود {records_msg} مرتبطة به. '
                    'يمكنك تعطيل حساب العميل بدلاً من حذفه.'
                )
                messages.error(request, msg)
            return redirect('customers:customer_detail', pk=customer.pk)
        except Exception as e:
            msg = f'حدث خطأ أثناء محاولة حذف العميل: {str(e)}'
            messages.error(request, msg)
            return redirect('customers:customer_detail', pk=customer.pk)

    context = {'customer': customer}
    return render(request, 'customers/customer_confirm_delete.html', context)

@login_required
@require_POST
def add_customer_note(request, pk):
    """
    View for adding a note to a customer
    """
    customer = get_object_or_404(Customer, pk=pk)
    form = CustomerNoteForm(request.POST)

    if form.is_valid():
        note = form.save(commit=False)
        note.customer = customer
        note.created_by = request.user
        note.save()
        messages.success(request, 'تمت إضافة الملاحظة بنجاح.')
    else:
        messages.error(request, 'حدث خطأ أثناء إضافة الملاحظة.')

    return redirect('customers:customer_detail', pk=pk)

@login_required
def delete_customer_note(request, customer_pk, note_pk):
    """
    View for deleting a customer note
    """
    note = get_object_or_404(CustomerNote, pk=note_pk, customer__pk=customer_pk)

    if request.method == 'POST':
        note.delete()
        messages.success(request, 'تم حذف الملاحظة بنجاح.')
        return JsonResponse({'status': 'success'})

    return JsonResponse({'status': 'error', 'message': 'طريقة طلب غير صالحة'})

@login_required
def customer_category_list(request):
    """
    View for displaying customer categories
    """
    categories = CustomerCategory.objects.all()
    context = {
        'categories': categories
    }
    return render(request, 'customers/category_list.html', context)

@login_required
def add_customer_category(request):
    """
    View for adding a new customer category
    """
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')

        if name:
            category = CustomerCategory.objects.create(
                name=name,
                description=description
            )
            return JsonResponse({
                'status': 'success',
                'category': {
                    'id': category.id,
                    'name': category.name
                }
            })

    return JsonResponse({'status': 'error', 'message': 'بيانات غير صالحة'})

@login_required
@require_POST
def delete_customer_category(request, category_id):
    """
    View for deleting a customer category
    """
    category = get_object_or_404(CustomerCategory, pk=category_id)

    # Only allow deletion if no customers are using this category
    if category.customers.exists():
        return JsonResponse({
            'status': 'error',
            'message': 'لا يمكن حذف التصنيف لأنه مرتبط بعملاء'
        })

    category.delete()
    return JsonResponse({'status': 'success'})

@login_required
def get_customer_notes(request, pk):
    """API endpoint to get customer notes"""
    customer = get_object_or_404(Customer, pk=pk)
    notes = customer.notes_history.all().order_by('-created_at')
    notes_data = [{
        'note': note.note,
        'created_at': note.created_at.strftime('%Y-%m-%d %H:%M'),
        'created_by': note.created_by.get_full_name() or note.created_by.username
    } for note in notes]

    return JsonResponse({'notes': notes_data})

@login_required
def get_customer_details(request, pk):
    """API endpoint to get customer details"""
    customer = get_object_or_404(Customer, pk=pk)

    customer_data = {
        'id': customer.id,
        'name': customer.name,
        'code': customer.code,
        'phone': customer.phone,
        'email': customer.email,
        'address': customer.address,
        'customer_type': customer.get_customer_type_display(),
        'status': customer.get_status_display()
    }

    return JsonResponse(customer_data)


class CustomerDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'customers/dashboard.html'

    def get_context_data(self, **kwargs):
        """
        تحسين أداء لوحة التحكم باستخدام استعلامات أكثر كفاءة
        """
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # استخدام select_related لتحميل البيانات المرتبطة مسبقًا
        if user.is_superuser:
            customers = Customer.objects.select_related('category', 'branch', 'created_by')
        else:
            customers = Customer.objects.select_related('category', 'branch', 'created_by').filter(branch=user.branch) if hasattr(user, 'branch') else Customer.objects.none()

        # استخدام استعلامات أكثر كفاءة
        from django.db.models import Count, Case, When, IntegerField

        # استخدام استعلام واحد للحصول على جميع الإحصائيات
        customer_stats = customers.aggregate(
            total=Count('id'),
            active=Count(Case(When(status='active', then=1), output_field=IntegerField())),
            inactive=Count(Case(When(status='inactive', then=1), output_field=IntegerField()))
        )

        context['total_customers'] = customer_stats['total']
        context['active_customers'] = customer_stats['active']
        context['inactive_customers'] = customer_stats['inactive']

        # تحميل العملاء الأخيرين مع البيانات المرتبطة
        context['recent_customers'] = customers.order_by('-created_at')[:10]

        return context

@login_required
def test_customer_form(request):
    """Test view for debugging customer form"""
    form = CustomerForm(user=request.user)
    return render(request, '../test_form.html', {'form': form})

def find_customer_by_phone(request):
    """API: البحث عن عميل برقم الهاتف وإرجاع بياناته JSON"""
    phone = request.GET.get('phone')
    if not phone:
        return JsonResponse({'found': False, 'error': 'رقم الهاتف مطلوب'}, status=400)
    customer = Customer.objects.filter(phone=phone).first()
    if customer:
        return JsonResponse({
            'found': True,
            'id': customer.pk,
            'name': customer.name,
            'branch': customer.branch.name if customer.branch else '',
            'phone': customer.phone,
            'email': customer.email,
            'address': customer.address,
            'url': f"/customers/{customer.pk}/"
        })
    return JsonResponse({'found': False})
