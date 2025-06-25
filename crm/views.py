"""
العرض الرئيسي للنظام
"""
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Count, Sum, F
from django.contrib import messages
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from customers.models import Customer
from orders.models import Order
from factory.models import ProductionOrder
from inventory.models import Product
from inspections.models import Inspection
from installations.models import Installation
from accounts.models import CompanyInfo, ContactFormSettings, AboutPageSettings, FooterSettings
import re

from django.http import HttpResponse, FileResponse, Http404
from django.conf import settings
import os
import mimetypes
from django.utils.encoding import smart_str

def home(request):
    """
    View for the home page
    """
    # Get counts for dashboard
    customers_count = Customer.objects.count()
    orders_count = Order.objects.count()
    production_count = ProductionOrder.objects.count()
    products_count = Product.objects.count()

    # Get recent orders
    recent_orders = Order.objects.select_related('customer').order_by('-order_date')[:5]

    # Get active production orders
    production_orders = ProductionOrder.objects.select_related(
        'order', 'production_line'
    ).exclude(
        status__in=['completed', 'cancelled']
    ).order_by('estimated_completion')[:5]    # Get low stock products
    low_stock_products = [
        product for product in Product.objects.all()
        if product.current_stock > 0 and product.current_stock <= product.minimum_stock
    ][:10]

    # Get company info for logo
    company_info = CompanyInfo.objects.first()
    if not company_info:
        company_info = CompanyInfo.objects.create(
            name='LATARA',
            version='1.0.0',
            release_date='2025-04-30',
            developer='zakee tahawi'
        )

    context = {
        'customers_count': customers_count,
        'orders_count': orders_count,
        'production_count': production_count,
        'products_count': products_count,
        'recent_orders': recent_orders,
        'production_orders': production_orders,
        'low_stock_products': low_stock_products,
        'current_year': timezone.now().year,
        'company_info': company_info,
    }

    return render(request, 'home.html', context)


def about(request):
    """
    View for the about page
    """
    # الحصول على إعدادات صفحة حول النظام أو إنشاء إعداد افتراضي إذا لم يكن موجودًا
    about_settings = AboutPageSettings.objects.first()
    if not about_settings:
        about_settings = AboutPageSettings.objects.create()

    # جلب معلومات الشركة (logo)
    company_info = CompanyInfo.objects.first()
    
    context = {
        'title': about_settings.title,
        'subtitle': about_settings.subtitle,
        'system_description': about_settings.system_description,
        'system_version': about_settings.system_version,
        'system_release_date': about_settings.system_release_date,
        'system_developer': about_settings.system_developer,
        'current_year': timezone.now().year,
        'company_info': company_info,  # إضافة معلومات الشركة للسياق
    }
    return render(request, 'about.html', context)

def contact(request):
    """
    View for the contact page
    """
    # الحصول على معلومات الشركة من CompanyInfo
    from accounts.models import CompanyInfo
    company_info = CompanyInfo.objects.first() or CompanyInfo.objects.create()

    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject')
        message = request.POST.get('message')

        if not all([name, email, subject, message]):
            messages.error(request, 'يرجى ملء جميع الحقول المطلوبة.')
        elif not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            messages.error(request, 'يرجى إدخال بريد إلكتروني صحيح.')
        else:
            # هنا يمكن إرسال البريد الإلكتروني فعليًا
            messages.success(request, 'تم إرسال رسالتك بنجاح. سنتواصل معك قريباً.')
            return redirect('contact')

    context = {
        'title': 'اتصل بنا',
        'description': company_info.description,
        'form_title': 'نموذج الاتصال',
        'company_info': company_info,
        'current_year': timezone.now().year,
    }
    return render(request, 'contact.html', context)

def serve_media_file(request, path):
    """
    Custom view to serve media files using FileResponse.
    Securely serves files from MEDIA_ROOT directory.
    """
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.exists(file_path):
        raise Http404("Media file not found")

    try:
        # استخدام mimetypes للكشف عن نوع الملف
        content_type, encoding = mimetypes.guess_type(file_path)
        content_type = content_type or 'application/octet-stream'

        # فتح الملف كـ binary stream
        file = open(file_path, 'rb')

        # إنشاء FileResponse مع streaming content
        response = FileResponse(file, content_type=content_type)

        # إعداد headers مناسبة للملف
        filename = os.path.basename(file_path)
        response['Content-Disposition'] = f'inline; filename="{smart_str(filename)}"'

        # إضافة headers إضافية للPDF
        if content_type == 'application/pdf':
            response['Accept-Ranges'] = 'bytes'
            response['Content-Length'] = os.path.getsize(file_path)

        return response
    except IOError:
        raise Http404("Error reading file")
    except Exception as e:
        if 'file' in locals():
            file.close()
        raise Http404(f"Error processing file: {str(e)}")

def data_management_redirect(request):
    """
    إعادة توجيه من المسارات القديمة إلى المسار الجديد لإدارة قواعد البيانات
    """
    return redirect('odoo_db_manager:dashboard')

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_api(request):
    """API endpoint for dashboard data"""
    today = timezone.now().date()
    data = {
        'customers': {
            'total': Customer.objects.count(),
            'active': Customer.objects.filter(status='active').count()
        },
        'orders': {
            'total': Order.objects.count(),
            'pending': Order.objects.filter(status='pending').count(),
            'completed': Order.objects.filter(status='completed').count(),
            'recent': list(Order.objects.select_related('customer')
                         .order_by('-created_at')[:5]
                         .values('id', 'customer__name', 'total_amount', 'status'))
        },
        'inventory': {
            'total_products': Product.objects.count(),
            'low_stock': Product.objects.filter(current_stock__lte=F('minimum_stock')).count()
        },
        'production': {
            'active_orders': ProductionOrder.objects.exclude(status__in=['completed', 'cancelled']).count(),
            'completed_today': ProductionOrder.objects.filter(completed_at__date=today).count()
        },
        'inspections': {
            'pending': Inspection.objects.filter(status='pending').count(),
            'completed': Inspection.objects.filter(status='completed').count()
        },
        'installations': {
            'pending': Installation.objects.filter(status='pending').count(),
            'completed': Installation.objects.filter(status='completed').count()
        }
    }
    return Response(data)
