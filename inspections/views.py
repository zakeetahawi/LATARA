from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count, F
from django.http import JsonResponse
from .models import Inspection, InspectionReport, InspectionNotification, InspectionEvaluation
from .forms import InspectionForm, InspectionReportForm, InspectionNotificationForm, InspectionEvaluationForm

from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext_lazy as _

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'inspections/dashboard.html'

    def get_context_data(self, **kwargs):
        from django.core.cache import cache
        from accounts.models import Branch
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        branch_id = self.request.GET.get('branch')

        # إنشاء مفتاح تخزين مؤقت فريد
        cache_key = f'dashboard_stats_{"all" if not branch_id else branch_id}_{today}'
        dashboard_data = cache.get(cache_key)

        if dashboard_data is None:
            # إذا لم تكن البيانات في التخزين المؤقت، قم بحسابها
            # تحسين الاستعلام باستخدام select_related للعلاقات المستخدمة بكثرة
            inspections = Inspection.objects.select_related('customer', 'branch', 'inspector')

            if branch_id:
                try:
                    branch_id = int(branch_id)
                    inspections = inspections.filter(branch_id=branch_id)
                    context['selected_branch'] = branch_id
                except (ValueError, TypeError):
                    context['selected_branch'] = None
            else:
                context['selected_branch'] = None

            # استخدام filter بدلاً من عمل استعلامات متعددة
            pending_inspections = inspections.filter(status='pending')

            # حساب عدد المعاينات بحسب الحالة
            new_inspections_count = pending_inspections.filter(
                scheduled_date__gt=today
            ).count()
            completed_inspections_count = inspections.filter(
                status='completed'
            ).count()
            in_progress_inspections_count = pending_inspections.filter(
                scheduled_date=today
            ).count()
            overdue_inspections_count = pending_inspections.filter(
                scheduled_date__lt=today
            ).count()

            # تخزين النتائج في كاش لمدة 10 دقائق (600 ثانية)
            dashboard_data = {
                'new_inspections_count': new_inspections_count,
                'completed_inspections_count': completed_inspections_count,
                'in_progress_inspections_count': in_progress_inspections_count,
                'overdue_inspections_count': overdue_inspections_count,
            }
            cache.set(cache_key, dashboard_data, 600)  # 10 دقائق

        # إضافة البيانات المخزنة مؤقتاً إلى السياق
        context.update(dashboard_data)
        context['branches'] = Branch.objects.all()

        return context

class CompletedInspectionsDetailView(LoginRequiredMixin, ListView):
    model = Inspection
    template_name = 'inspections/completed_details.html'
    context_object_name = 'inspections'
    paginate_by = 20

    def get_queryset(self):
        queryset = Inspection.objects.filter(status='completed')
        if not self.request.user.is_superuser:
            queryset = queryset.filter(
                Q(inspector=self.request.user) | Q(created_by=self.request.user)
            )
        return queryset.select_related('customer', 'inspector', 'branch')

class CancelledInspectionsDetailView(LoginRequiredMixin, ListView):
    model = Inspection
    template_name = 'inspections/cancelled_details.html'
    context_object_name = 'inspections'
    paginate_by = 20

    def get_queryset(self):
        queryset = Inspection.objects.filter(status='cancelled')
        if not self.request.user.is_superuser:
            queryset = queryset.filter(
                Q(inspector=self.request.user) | Q(created_by=self.request.user)
            )
        return queryset.select_related('customer', 'inspector', 'branch')

class PendingInspectionsDetailView(LoginRequiredMixin, ListView):
    model = Inspection
    template_name = 'inspections/pending_details.html'
    context_object_name = 'inspections'
    paginate_by = 20

    def get_queryset(self):
        queryset = Inspection.objects.filter(status='pending')
        if not self.request.user.is_superuser:
            queryset = queryset.filter(
                Q(inspector=self.request.user) | Q(created_by=self.request.user)
            )
        return queryset.select_related('customer', 'inspector', 'branch')

class InspectionListView(LoginRequiredMixin, ListView):
    model = Inspection
    template_name = 'inspections/inspection_list.html'
    context_object_name = 'inspections'
    paginate_by = 10

    def get_queryset(self):
        queryset = Inspection.objects.all() if self.request.user.is_superuser else Inspection.objects.filter(
            Q(inspector=self.request.user) | Q(created_by=self.request.user)
        )

        # Branch filter
        branch_id = self.request.GET.get('branch')
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)

        # Status and other filters
        status = self.request.GET.get('status')
        from_orders = self.request.GET.get('from_orders')
        is_duplicated = self.request.GET.get('is_duplicated')
        today = timezone.now().date()

        if status == 'pending' and from_orders == '1':
            queryset = queryset.filter(status='pending', is_from_orders=True)
        elif status:
            queryset = queryset.filter(status=status)

        # Filter for duplicated inspections
        if is_duplicated == '1':
            # Find inspections where notes contain text indicating they are duplicates
            queryset = queryset.filter(notes__contains='تكرار من المعاينة رقم:')

        return queryset.select_related('customer', 'inspector', 'branch')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from accounts.models import Branch

        # تحسين استخدام استعلام واحد لجميع إحصائيات المعاينات باستخدام annotate
        from django.db.models import Count, Case, When, IntegerField

        # استخدام قاعدة بيانات بحيث تكون أكثر كفاءة
        inspections = Inspection.objects.all()
        if not self.request.user.is_superuser:
            inspections = inspections.filter(
                Q(inspector=self.request.user) | Q(created_by=self.request.user)
            )

        # Branch filter for stats
        branch_id = self.request.GET.get('branch')
        if branch_id:
            inspections = inspections.filter(branch_id=branch_id)

        # استخدام طريقة أكثر كفاءة لحساب الإحصائيات - استعلام واحد بدلاً من عدة استعلامات
        stats = inspections.aggregate(
            total_inspections=Count('id'),
            new_inspections=Count(Case(
                When(status='pending', then=1),
                output_field=IntegerField(),
            )),
            scheduled_inspections=Count(Case(
                When(status='scheduled', then=1),
                output_field=IntegerField(),
            )),
            successful_inspections=Count(Case(
                When(status='completed', then=1),
                output_field=IntegerField(),
            )),
            cancelled_inspections=Count(Case(
                When(status='cancelled', then=1),
                output_field=IntegerField(),
            )),
        )

        # حساب المعاينات المكررة
        duplicated_inspections = inspections.filter(notes__contains='تكرار من المعاينة رقم:').count()
        stats['duplicated_inspections'] = duplicated_inspections

        context['dashboard'] = stats

        # Add branches for filter
        context['branches'] = Branch.objects.all()
        return context

class InspectionCreateView(LoginRequiredMixin, CreateView):
    model = Inspection
    form_class = InspectionForm
    template_name = 'inspections/inspection_form.html'
    success_url = reverse_lazy('inspections:inspection_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        # إضافة الطلب المرتبط إلى النموذج إذا كان موجوداً
        order_id = self.request.GET.get('order_id')
        if order_id:
            from orders.models import Order
            try:
                kwargs['order'] = Order.objects.get(id=order_id)
            except Order.DoesNotExist:
                pass
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        if not form.instance.inspector:
            form.instance.inspector = self.request.user
        if not form.instance.branch and not self.request.user.is_superuser:
            form.instance.branch = self.request.user.branch

        # حفظ البائع من الطلب المرتبط
        order_id = self.request.GET.get('order_id')
        if order_id:
            from orders.models import Order
            try:
                order = Order.objects.get(id=order_id)
                form.instance.order = order
                form.instance.is_from_orders = True

                # تعيين البائع بشكل صريح من الطلب المرتبط
                if order.salesperson:
                    form.instance.responsible_employee = order.salesperson
                    # تأكد من حفظ المعاينة قبل عرضها

                # نسخ معلومات أخرى من الطلب
                if not form.instance.customer and order.customer:
                    form.instance.customer = order.customer
                if not form.instance.contract_number and order.contract_number:
                    form.instance.contract_number = order.contract_number

            except Order.DoesNotExist:
                pass

        # حفظ المعاينة
        messages.success(self.request, 'تم إنشاء المعاينة بنجاح')
        response = super().form_valid(form)

        # للتأكد من حفظ معلومات البائع، نقوم بتحديثها مرة أخرى بعد الحفظ إذا كانت من طلب
        if order_id and hasattr(form.instance, 'order') and form.instance.order and form.instance.order.salesperson:
            if not form.instance.responsible_employee:
                form.instance.responsible_employee = form.instance.order.salesperson
                form.instance.save(update_fields=['responsible_employee'])

        return response

class InspectionDetailView(LoginRequiredMixin, DetailView):
    model = Inspection
    template_name = 'inspections/inspection_detail.html'
    context_object_name = 'inspection'

    def get_queryset(self):
        return super().get_queryset().select_related('customer', 'inspector', 'branch', 'created_by', 'order')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        inspection = self.get_object()

        # إضافة ملاحظات العميل إذا كان موجودًا
        if inspection.customer:
            from customers.models import CustomerNote
            context['customer_notes'] = CustomerNote.objects.filter(
                customer=inspection.customer
            ).order_by('-created_at')[:5]

        # تخزين ملاحظات الطلب في سياق الصفحة حتى إذا تم تحميلها بشكل غير متزامن
        if hasattr(inspection, 'order') and inspection.order:
            context['order_notes'] = inspection.order.notes

        return context

class InspectionUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Inspection
    form_class = InspectionForm
    template_name = 'inspections/inspection_form.html'
    success_url = reverse_lazy('inspections:inspection_list')

    def test_func(self):
        inspection = self.get_object()
        return (self.request.user.is_superuser or
                inspection.created_by == self.request.user or
                inspection.inspector == self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user

        # إضافة الطلب المرتبط إلى النموذج إذا كان موجوداً
        inspection = self.get_object()
        if hasattr(inspection, 'order') and inspection.order:
            kwargs['order'] = inspection.order

        return kwargs

    def form_valid(self, form):
        inspection = form.instance
        old_inspection = self.get_object()
        old_status = old_inspection.status

        # Safely get the new status, falling back to the instance's status if not in form
        new_status = form.cleaned_data.get('status', inspection.status)

        # Save inspection first to ensure it exists
        response = super().form_valid(form)

        # Try to get order if it exists
        try:
            if inspection.order:
                if new_status == 'completed':
                    inspection.order.tracking_status = 'processing'
                elif new_status == 'scheduled':
                    inspection.order.tracking_status = 'processing'
                elif new_status == 'cancelled':
                    inspection.order.tracking_status = 'pending'
                else:  # pending
                    inspection.order.tracking_status = 'pending'

                inspection.order.save()
                messages.success(self.request, 'تم تحديث حالة المعاينة والطلب المرتبط')
                return redirect('orders:order_detail', inspection.order.pk)
        except AttributeError:
            # No order associated with this inspection
            pass

        # Handle completion status - let the model handle this via the tracker
        # We don't need to manually set completed_at here anymore
        if new_status == 'completed' and old_status != 'completed':
            if not hasattr(inspection, 'evaluation'):
                return redirect('inspections:evaluation_create', inspection_pk=inspection.pk)

        messages.success(self.request, 'تم تحديث حالة المعاينة بنجاح')
        return response

    def handle_no_permission(self):
        messages.error(self.request, 'ليس لديك صلاحية لتعديل هذه المعاينة')
        return redirect('inspections:inspection_list')

class InspectionDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Inspection
    success_url = reverse_lazy('inspections:inspection_list')
    template_name = 'inspections/inspection_confirm_delete.html'

    def test_func(self):
        inspection = self.get_object()
        return self.request.user.is_superuser or inspection.created_by == self.request.user

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'تم حذف المعاينة بنجاح')
        return super().delete(request, *args, **kwargs)

    def handle_no_permission(self):
        messages.error(self.request, 'ليس لديك صلاحية لحذف هذه المعاينة')
        return redirect('inspections:inspection_list')

class EvaluationCreateView(LoginRequiredMixin, CreateView):
    form_class = InspectionEvaluationForm
    template_name = 'inspections/evaluation_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop('instance', None)
        return kwargs

    def form_valid(self, form):
        inspection = get_object_or_404(Inspection, pk=self.kwargs['inspection_pk'])
        notes = form.cleaned_data.get('notes', '')
        user = self.request.user
        created = 0
        with transaction.atomic():
            for criteria in ['location', 'condition', 'suitability', 'safety', 'accessibility']:
                rating = form.cleaned_data.get(criteria)
                if rating:
                    InspectionEvaluation.objects.create(
                        inspection=inspection,
                        criteria=criteria,
                        rating=rating,
                        notes=notes,
                        created_by=user
                    )
                    created += 1
        if created:
            messages.success(self.request, f'تم إضافة {created} تقييمات للمعاينة بنجاح')
        else:
            messages.warning(self.request, 'لم يتم إضافة أي تقييمات')
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy('inspections:inspection_detail', kwargs={'pk': self.kwargs['inspection_pk']})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['inspection'] = get_object_or_404(Inspection, pk=self.kwargs['inspection_pk'])
        return context

class InspectionReportCreateView(LoginRequiredMixin, CreateView):
    model = InspectionReport
    form_class = InspectionReportForm
    template_name = 'inspections/inspection_report_form.html'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        self.object.calculate_statistics()
        messages.success(self.request, 'تم إنشاء تقرير المعاينات بنجاح')
        return response

    def get_success_url(self):
        return reverse('inspections:inspection_list')

class NotificationListView(LoginRequiredMixin, ListView):
    model = InspectionNotification
    template_name = 'inspections/notifications/notification_list.html'  # Updated path
    context_object_name = 'notifications'
    paginate_by = 10

    def get_queryset(self):
        return InspectionNotification.objects.filter(
            recipient=self.request.user
        ).order_by('-created_at')

class NotificationCreateView(LoginRequiredMixin, CreateView):
    model = InspectionNotification
    form_class = InspectionNotificationForm
    template_name = 'inspections/notifications/notification_form.html'  # Updated path

    def form_valid(self, form):
        inspection = get_object_or_404(Inspection, pk=self.kwargs['inspection_pk'])
        form.instance.inspection = inspection
        form.instance.sender = self.request.user
        messages.success(self.request, 'تم إرسال الإشعار بنجاح')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('inspections:inspection_detail', kwargs={'pk': self.kwargs['inspection_pk']})

def mark_notification_read(request, pk):
    notification = get_object_or_404(InspectionNotification, pk=pk)
    if request.user == notification.recipient:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        messages.success(request, 'تم تحديث حالة الإشعار')
    return redirect('inspections:notification_list')

@login_required
def iterate_inspection(request, pk):
    """
    Create a new inspection as an iteration of a completed inspection.
    This allows for continued follow-up on completed inspections.
    """
    try:
        # Get the original inspection
        original_inspection = get_object_or_404(Inspection, pk=pk)

        # Verify the inspection is completed
        if original_inspection.status != 'completed':
            messages.error(request, _('يمكن فقط تكرار المعاينات المكتملة.'))
            return redirect('inspections:inspection_detail', pk=pk)

        # Create a new inspection based on the original
        new_inspection = Inspection(
            customer=original_inspection.customer,
            branch=original_inspection.branch,
            inspector=original_inspection.inspector,
            responsible_employee=original_inspection.responsible_employee,
            is_from_orders=original_inspection.is_from_orders,
            windows_count=original_inspection.windows_count,
            request_date=timezone.now().date(),
            scheduled_date=timezone.now().date() + timezone.timedelta(days=1),  # Schedule for tomorrow
            status='pending',
            notes=_('تكرار من المعاينة رقم: {0}\nملاحظات المعاينة السابقة:\n{1}').format(
                original_inspection.contract_number,
                original_inspection.notes
            ),
            order_notes=original_inspection.order_notes,
            created_by=request.user,
            order=original_inspection.order
        )

        # Generate a new contract number
        new_inspection.contract_number = None  # Will be auto-generated on save
        new_inspection.save()

        messages.success(request, _('تم إنشاء معاينة جديدة كتكرار للمعاينة السابقة بنجاح.'))
        return redirect('inspections:inspection_detail', pk=new_inspection.pk)

    except Exception as e:
        messages.error(request, _('حدث خطأ أثناء تكرار المعاينة: {0}').format(str(e)))
        return redirect('inspections:inspection_detail', pk=pk)

@login_required
def ajax_duplicate_inspection(request):
    """
    AJAX endpoint for duplicating an inspection from the modal window.
    """
    if request.method == 'POST':
        try:
            # Get parameters from request
            inspection_id = request.POST.get('inspection_id')
            scheduled_date = request.POST.get('scheduled_date')
            additional_notes = request.POST.get('additional_notes', '')

            # Validate parameters
            if not inspection_id or not scheduled_date:
                return JsonResponse({
                    'success': False,
                    'error': _('معلومات ناقصة. الرجاء تحديد المعاينة وتاريخ التنفيذ.')
                })

            # Get the original inspection
            original_inspection = get_object_or_404(Inspection, pk=inspection_id)

            # Verify the inspection is completed
            if original_inspection.status != 'completed':
                return JsonResponse({
                    'success': False,
                    'error': _('يمكن فقط تكرار المعاينات المكتملة.')
                })

            # Format notes
            notes = _('تكرار من المعاينة رقم: {0}\nملاحظات المعاينة السابقة:\n{1}').format(
                original_inspection.contract_number,
                original_inspection.notes
            )

            # Add additional notes if provided
            if additional_notes:
                notes += f"\n\n{_('ملاحظات إضافية:')}\n{additional_notes}"

            # Create a new inspection based on the original
            with transaction.atomic():
                new_inspection = Inspection(
                    customer=original_inspection.customer,
                    branch=original_inspection.branch,
                    inspector=original_inspection.inspector,
                    responsible_employee=original_inspection.responsible_employee,
                    is_from_orders=original_inspection.is_from_orders,
                    windows_count=original_inspection.windows_count,
                    request_date=timezone.now().date(),
                    scheduled_date=scheduled_date,  # Use the date from the modal
                    status='pending',
                    notes=notes,
                    order_notes=original_inspection.order_notes,
                    created_by=request.user,
                    order=original_inspection.order
                )

                # Generate a new contract number
                new_inspection.contract_number = None  # Will be auto-generated on save
                new_inspection.save()

            return JsonResponse({
                'success': True,
                'inspection_id': new_inspection.id,
                'message': _('تم إنشاء معاينة جديدة كتكرار للمعاينة السابقة بنجاح.'),
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    else:
        return JsonResponse({
            'success': False,
            'error': _('طريقة الطلب غير مدعومة.')
        })
