from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Order, OrderItem, Payment
from .forms import OrderForm, OrderItemFormSet, PaymentForm
from accounts.models import Branch, Salesperson, Department, Notification, SystemSettings
from customers.models import Customer
from inventory.models import Product
from inspections.models import Inspection
from datetime import datetime, timedelta

class OrdersDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'orders/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()

        # Get orders
        if self.request.user.is_superuser:
            orders = Order.objects.all()
        else:
            orders = Order.objects.filter(Q(created_by=self.request.user) | Q(salesperson=self.request.user))

        # Basic statistics
        context['total_orders'] = orders.count()
        context['pending_orders'] = orders.filter(status='pending').count()
        context['completed_orders'] = orders.filter(status='completed').count()
        context['recent_orders'] = orders.order_by('-created_at')[:10]

        # Sales statistics
        context['total_sales'] = orders.filter(status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        context['monthly_sales'] = orders.filter(created_at__month=today.month).aggregate(Sum('total_amount'))['total_amount__sum'] or 0

        return context

@login_required
def order_list(request):
    """
    View for displaying the list of orders with search and filtering
    """
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    # Filter orders based on search query and status
    orders = Order.objects.all().select_related('customer', 'salesperson')

    if search_query:
        orders = orders.filter(
            Q(order_number__icontains=search_query) |
            Q(customer__name__icontains=search_query)
        )

    if status_filter:
        orders = orders.filter(status=status_filter)

    # Order by created_at
    orders = orders.order_by('-created_at')

    # Pagination
    paginator = Paginator(orders, 10)  # Show 10 orders per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get currency symbol from system settings
    system_settings = SystemSettings.get_settings()
    currency_symbol = system_settings.currency_symbol if system_settings else 'ج.م'

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_orders': orders.count(),
        'currency_symbol': currency_symbol,  # Add currency symbol to context
    }

    return render(request, 'orders/order_list.html', context)

@login_required
def order_detail(request, pk):
    """
    View for displaying order details
    """
    order = get_object_or_404(Order, pk=pk)
    payments = order.payments.all().order_by('-payment_date')

    # Now all information is in the Order model
    order_items = order.items.all()

    # Get inspections related to this order
    inspections = []
    if 'inspection' in order.service_types:
        # Get inspections for this customer that were created after this order
        inspections = Inspection.objects.filter(
            customer=order.customer,
            created_at__gte=order.created_at
        ).order_by('-created_at')

    # Get currency symbol from system settings
    system_settings = SystemSettings.get_settings()
    currency_symbol = system_settings.currency_symbol if system_settings else 'ج.م'

    context = {
        'order': order,
        'payments': payments,
        'order_items': order_items,
        'inspections': inspections,
        'currency_symbol': currency_symbol,  # Add currency symbol to context
    }

    return render(request, 'orders/order_detail.html', context)

@login_required
@permission_required('orders.add_order', raise_exception=True)
def order_create(request):
    """
    View for creating a new order
    """
    customer_id = request.GET.get('customer_id')
    form = OrderForm(initial={'user': request.user})
    formset = OrderItemFormSet(prefix='items')

    if request.method == 'POST':
        form = OrderForm(request.POST, initial={'user': request.user})

        if form.is_valid():
            try:
                # Save order
                # 1. إنشاء كائن الطلب بدون حفظه
                order = form.save(commit=False)
                order.created_by = request.user

                # 2. تعيين الفرع إذا لم يتم توفيره
                if not order.branch:
                    order.branch = request.user.branch

                # 3. حفظ الطلب في قاعدة البيانات للحصول على مفتاح أساسي
                order.save()

                # التأكد من أن الطلب تم حفظه بنجاح وله مفتاح أساسي
                if not order.pk:
                    raise Exception("فشل في حفظ الطلب: لم يتم إنشاء مفتاح أساسي")

                # 4. معالجة المنتجات المحددة إن وجدت
                selected_products_json = request.POST.get('selected_products', '')
                if selected_products_json:
                    import json
                    try:
                        selected_products = json.loads(selected_products_json)

                        for product_data in selected_products:
                            try:
                                product_id = product_data.get('id')
                                quantity = product_data.get('quantity', 1)

                                product = Product.objects.get(id=product_id)

                                # التحقق من نوع المنتج
                                product_type = 'fabric' if product.category and 'قماش' in product.category.name.lower() else 'accessory'

                                # إنشاء عنصر الطلب
                                OrderItem.objects.create(
                                    order=order,
                                    product=product,
                                    quantity=quantity,
                                    unit_price=product.price or 0,
                                    item_type=product_type
                                )
                                print(f"تم إنشاء عنصر الطلب بنجاح: {product.name}")
                            except Product.DoesNotExist:
                                print(f"Product {product_id} does not exist")
                            except Exception as e:
                                print(f"Error creating order item: {e}")
                    except json.JSONDecodeError:
                        print("Invalid JSON for selected products")

                # 5. إذا كان الطلب يتضمن خدمة معاينة، قم بإنشاء سجل معاينة جديد
                if 'inspection' in form.cleaned_data.get('selected_types', []):
                    try:
                        # إنشاء معاينة جديدة
                        inspection = Inspection.objects.create(
                            customer=order.customer,
                            branch=order.branch,
                            request_date=datetime.now().date(),
                            scheduled_date=datetime.now().date() + timedelta(days=3),
                            status='pending',
                            notes=f'تم إنشاء المعاينة تلقائياً من الطلب رقم {order.order_number}',
                            created_by=request.user,
                            is_from_orders=True,  # إضافة هذه العلامة
                            order=order  # الربط بالطلب
                        )
                        print(f"تم إنشاء معاينة جديدة بنجاح للطلب {order.order_number}")

                        # إنشاء إشعار لقسم المعاينات
                        dept = Department.objects.filter(code='inspections').first()
                        if dept:
                            Notification.objects.create(
                                title='طلب معاينة جديد',
                                message=f'تم إنشاء طلب معاينة جديد للعميل {order.customer.name} من الطلب {order.order_number}',
                                priority='high',
                                sender=request.user,
                                target_department=dept,
                                target_branch=order.branch
                            )
                    except Exception as e:
                        print(f"Error creating inspection: {e}")
                        messages.warning(request, f'تم إنشاء الطلب بنجاح ولكن فشل إنشاء المعاينة: {str(e)}')

                # 6. الآن نقوم بمعالجة الـ formset بعد حفظ الطلب
                formset = OrderItemFormSet(request.POST, prefix='items', instance=order)
                if formset.is_valid():
                    formset.save()
                else:
                    print("Formset errors:", formset.errors)

                messages.success(request, 'تم إنشاء الطلب بنجاح!')
                return redirect('orders:order_detail', pk=order.pk)

            except Exception as e:
                messages.error(request, f'حدث خطأ أثناء حفظ الطلب: {str(e)}')
                return render(request, 'orders/order_form.html', {'form': form, 'formset': formset})

    customer = None
    last_order = None

    if customer_id:
        try:
            customer = Customer.objects.get(id=customer_id)
            last_order = Order.objects.filter(customer=customer).order_by('-created_at').first()

            if form and 'customer' in form.fields:
                form.fields['customer'].initial = customer.id
        except Customer.DoesNotExist:
            pass

    context = {
        'form': form,
        'formset': formset,
        'title': 'إنشاء طلب جديد',
        'customer': customer,
        'last_order': last_order,
    }

    return render(request, 'orders/order_form.html', context)

@login_required
@permission_required('orders.change_order', raise_exception=True)
def order_update(request, pk):
    """
    View for updating an existing order
    """
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        # Print request.POST for debugging
        print("UPDATE - POST data:", request.POST)

        form = OrderForm(request.POST, instance=order)

        # Print form errors if any
        if not form.is_valid():
            print("UPDATE - Form errors:", form.errors)
            messages.error(request, 'يوجد أخطاء في النموذج. يرجى التحقق من البيانات المدخلة.')
            return render(request, 'orders/order_form.html', {
                'form': form,
                'formset': OrderItemFormSet(request.POST, prefix='items', instance=order),
                'title': f'تحديث الطلب: {order.order_number}',
                'order': order,
            })

        try:
            # Save order
            order = form.save(commit=False)

            # Handle delivery options
            delivery_option = request.POST.get('delivery_option')
            if delivery_option == 'home':
                order.delivery_type = 'home'
                order.delivery_address = request.POST.get('delivery_address', '')
            elif delivery_option == 'branch':
                order.delivery_type = 'branch'
                # Branch is already set in the form

            # Handle order type field
            order_types = request.POST.get('order_type_hidden', '')
            if order_types:
                order_types = [ot.strip() for ot in order_types.split(',') if ot.strip()]
                if order_types:  # Check if there are any valid order types
                    # Set the first order type as the primary type
                    order.order_type = order_types[0]
            else:
                # Fallback to radio button value
                order_type = request.POST.get('order_type', '')
                if order_type:
                    order.order_type = order_type

            # Handle service_types field
            if order_types and 'service' in order_types:
                service_types = request.POST.get('service_types_hidden', '')
                if service_types:
                    service_types = [st.strip() for st in service_types.split(',') if st.strip()]
                    order.service_types = service_types

            # حفظ الطلب
            order.save()

            # التأكد من أن الطلب تم حفظه بنجاح وله مفتاح أساسي
            if not order.pk:
                raise Exception("فشل في حفظ الطلب: لم يتم إنشاء مفتاح أساسي")

            # Save order items
            formset = OrderItemFormSet(request.POST, prefix='items', instance=order)
            if formset.is_valid():
                formset.save()
            else:
                print("UPDATE - Formset errors:", formset.errors)
                messages.warning(request, 'تم تحديث الطلب ولكن هناك أخطاء في عناصر الطلب.')

            messages.success(request, 'تم تحديث الطلب بنجاح!')
            return redirect('orders:order_detail', pk=order.pk)

        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء تحديث الطلب: {str(e)}')
            return render(request, 'orders/order_form.html', {
                'form': form,
                'formset': OrderItemFormSet(request.POST, prefix='items', instance=order),
                'title': f'تحديث الطلب: {order.order_number}',
                'order': order,
            })

    form = OrderForm(instance=order)
    formset = OrderItemFormSet(instance=order)

    context = {
        'form': form,
        'formset': formset,
        'title': f'تحديث الطلب: {order.order_number}',
        'order': order,
    }

    return render(request, 'orders/order_form.html', context)

@login_required
@permission_required('orders.delete_order', raise_exception=True)
def order_delete(request, pk):
    """
    View for deleting an order
    """
    order = get_object_or_404(Order, pk=pk)

    if request.method == 'POST':
        try:
            order.delete()
            messages.success(request, 'تم حذف الطلب بنجاح.')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء حذف الطلب: {str(e)}')
        return redirect('orders:order_list')

    context = {
        'order': order,
        'title': f'حذف الطلب: {order.order_number}',
    }

    return render(request, 'orders/order_confirm_delete.html', context)

@login_required
@permission_required('orders.add_payment', raise_exception=True)
def payment_create(request, order_pk):
    """
    View for creating a new payment for an order
    """
    order = get_object_or_404(Order, pk=order_pk)

    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                # التأكد من أن الطلب له مفتاح أساسي
                if not order.pk:
                    messages.error(request, 'لا يمكن إنشاء دفعة: الطلب ليس له مفتاح أساسي')
                    return redirect('orders:order_detail', pk=order_pk)

                payment = form.save(commit=False)
                payment.order = order
                payment.created_by = request.user
                payment.save()

                messages.success(request, 'تم تسجيل الدفعة بنجاح.')
                return redirect('orders:order_detail', pk=order.pk)
            except Exception as e:
                messages.error(request, f'حدث خطأ أثناء حفظ الدفعة: {str(e)}')
                return render(request, 'orders/payment_form.html', {'form': form, 'order': order})
    else:
        form = PaymentForm()

    # Get currency symbol from system settings
    system_settings = SystemSettings.get_settings()
    currency_symbol = system_settings.currency_symbol if system_settings else 'ج.م'

    context = {
        'form': form,
        'order': order,
        'title': f'تسجيل دفعة جديدة للطلب: {order.order_number}',
        'currency_symbol': currency_symbol,  # Add currency symbol to context
    }

    return render(request, 'orders/payment_form.html', context)

@login_required
@permission_required('orders.delete_payment', raise_exception=True)
def payment_delete(request, pk):
    """
    View for deleting a payment
    """
    payment = get_object_or_404(Payment, pk=pk)
    order = payment.order

    if request.method == 'POST':
        try:
            payment.delete()
            messages.success(request, 'تم حذف الدفعة بنجاح.')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء حذف الدفعة: {str(e)}')
        return redirect('orders:order_detail', pk=order.pk)

    context = {
        'payment': payment,
        'order': order,
        'title': f'حذف دفعة من الطلب: {order.order_number}'
    }

    return render(request, 'orders/payment_confirm_delete.html', context)

@login_required
def salesperson_list(request):
    """
    View for listing salespersons and their orders
    """
    salespersons = Salesperson.objects.all()

    # Add order statistics for each salesperson
    for sp in salespersons:
        sp.total_orders = Order.objects.filter(salesperson=sp).count()
        sp.completed_orders = Order.objects.filter(salesperson=sp, status='completed').count()
        sp.pending_orders = Order.objects.filter(salesperson=sp, status='pending').count()
        sp.total_sales = Order.objects.filter(salesperson=sp, status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0

    context = {
        'salespersons': salespersons,
        'title': 'قائمة مندوبي المبيعات'
    }

    return render(request, 'orders/salesperson_list.html', context)

@login_required
@permission_required('orders.change_order', raise_exception=True)
def update_order_status(request, order_id):
    """
    View for updating order status
    """
    order = get_object_or_404(Order, pk=order_id)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status and new_status in dict(Order.STATUS_CHOICES).keys():
            try:
                # التأكد من أن الطلب له مفتاح أساسي
                if not order.pk:
                    messages.error(request, 'لا يمكن تحديث حالة الطلب: الطلب ليس له مفتاح أساسي')
                    return redirect('orders:order_detail', pk=order_id)

                order.status = new_status
                order.save()
                messages.success(request, 'تم تحديث حالة الطلب بنجاح.')
            except Exception as e:
                messages.error(request, f'حدث خطأ أثناء تحديث حالة الطلب: {str(e)}')
        else:
            messages.error(request, 'حالة الطلب غير صالحة.')

    return redirect('orders:order_detail', pk=order_id)
