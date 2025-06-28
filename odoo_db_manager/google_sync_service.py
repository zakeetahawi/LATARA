"""
خدمة مزامنة Google Sheets المحسنة
Enhanced Google Sheets Sync Service
"""

import logging
import json
from typing import Dict, List, Any, Optional, Tuple
from django.utils import timezone
from django.db import transaction
from django.apps import apps
from django.core.exceptions import ValidationError

from .google_sync import GoogleSyncConfig, GoogleSyncLog, create_sheets_service, update_sheet

logger = logging.getLogger('odoo_db_manager.google_sync_service')


class GoogleSyncService:
    """خدمة مزامنة Google Sheets المحسنة"""
    
    def __init__(self, config: GoogleSyncConfig = None):
        self.config = config or GoogleSyncConfig.get_active_config()
        self.service = None
        self.stats = {
            'total_synced': 0,
            'successful_syncs': 0,
            'failed_syncs': 0,
            'errors': []
        }
    
    def initialize_service(self) -> bool:
        """تهيئة خدمة Google Sheets"""
        try:
            if not self.config:
                logger.error("لا يوجد إعداد مزامنة نشط")
                return False
            
            credentials = self.config.get_credentials()
            if not credentials:
                logger.error("فشل الحصول على بيانات الاعتماد")
                return False
            
            self.service = create_sheets_service(credentials)
            if not self.service:
                logger.error("فشل إنشاء خدمة Google Sheets")
                return False
            
            # اختبار الوصول إلى جدول البيانات
            try:
                self.service.spreadsheets().get(spreadsheetId=self.config.spreadsheet_id).execute()
                logger.info("تم تهيئة خدمة Google Sheets بنجاح")
                return True
            except Exception as e:
                logger.error(f"فشل الوصول إلى جدول البيانات: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"خطأ في تهيئة خدمة Google Sheets: {str(e)}")
            return False
    
    def sync_all_data(self, selected_tables: List[str] = None) -> Dict[str, Any]:
        """مزامنة جميع البيانات أو الجداول المحددة"""
        try:
            if not self.initialize_service():
                return {'status': 'error', 'message': 'فشل تهيئة خدمة Google Sheets'}
            
            results = {}
            sync_functions = {
                'databases': self._sync_databases,
                'users': self._sync_users,
                'customers': self._sync_customers,
                'orders': self._sync_orders,
                'products': self._sync_products,
                'inspections': self._sync_inspections,
                'settings': self._sync_settings,
                'branches': self._sync_branches
            }
            
            # تحديد الجداول المراد مزامنتها
            tables_to_sync = selected_tables if selected_tables else list(sync_functions.keys())
            
            for table_name in tables_to_sync:
                if table_name in sync_functions:
                    try:
                        logger.info(f"بدء مزامنة: {table_name}")
                        result = sync_functions[table_name]()
                        results[table_name] = result
                        
                        if result.get('status') == 'success':
                            self.stats['successful_syncs'] += 1
                        else:
                            self.stats['failed_syncs'] += 1
                            self.stats['errors'].append(f"{table_name}: {result.get('message', 'خطأ غير معروف')}")
                        
                        self.stats['total_synced'] += 1
                        
                    except Exception as e:
                        error_msg = f"خطأ في مزامنة {table_name}: {str(e)}"
                        logger.error(error_msg)
                        results[table_name] = {'status': 'error', 'message': error_msg}
                        self.stats['failed_syncs'] += 1
                        self.stats['errors'].append(error_msg)
            
            # تحديث وقت آخر مزامنة
            if self.config:
                self.config.update_last_sync()
            
            # تسجيل النتائج
            self._log_sync_results(results)
            
            return {
                'status': 'success' if self.stats['failed_syncs'] == 0 else 'partial',
                'message': f"تمت مزامنة {self.stats['successful_syncs']} من {self.stats['total_synced']} جدول",
                'results': results,
                'stats': self.stats
            }
            
        except Exception as e:
            error_msg = f"خطأ عام في المزامنة: {str(e)}"
            logger.error(error_msg)
            return {'status': 'error', 'message': error_msg}
    
    def _sync_databases(self) -> Dict[str, Any]:
        """مزامنة قواعد البيانات"""
        try:
            Database = apps.get_model('odoo_db_manager', 'Database')
            databases = Database.objects.all()
            
            data = [['الاسم', 'النوع', 'نشطة', 'حالة الاتصال', 'تاريخ الإنشاء']]
            
            for db in databases:
                data.append([
                    str(db.name),
                    str(db.get_db_type_display()),
                    'نعم' if db.is_active else 'لا',
                    'متصل' if db.connection_status else 'غير متصل',
                    db.created_at.strftime('%Y-%m-%d %H:%M') if db.created_at else ''
                ])
            
            updated_rows = update_sheet(self.service, self.config.spreadsheet_id, 'قواعد البيانات', data)
            return {'status': 'success', 'message': f"تمت مزامنة {updated_rows} قاعدة بيانات"}
            
        except Exception as e:
            return {'status': 'error', 'message': f"خطأ في مزامنة قواعد البيانات: {str(e)}"}
    
    def _sync_users(self) -> Dict[str, Any]:
        """مزامنة المستخدمين"""
        try:
            User = apps.get_model('accounts', 'User')
            users = User.objects.all()
            
            data = [['اسم المستخدم', 'الاسم الأول', 'الاسم الأخير', 'البريد الإلكتروني', 'نشط', 'موظف', 'مدير عام']]
            
            for user in users:
                data.append([
                    str(user.username),
                    str(user.first_name),
                    str(user.last_name),
                    str(user.email),
                    'نعم' if user.is_active else 'لا',
                    'نعم' if user.is_staff else 'لا',
                    'نعم' if user.is_superuser else 'لا'
                ])
            
            updated_rows = update_sheet(self.service, self.config.spreadsheet_id, 'المستخدمين', data)
            return {'status': 'success', 'message': f"تمت مزامنة {updated_rows} مستخدم"}
            
        except Exception as e:
            return {'status': 'error', 'message': f"خطأ في مزامنة المستخدمين: {str(e)}"}
    
    def _sync_customers(self) -> Dict[str, Any]:
        """مزامنة العملاء"""
        try:
            Customer = apps.get_model('customers', 'Customer')
            customers = Customer.objects.all()
            
            data = [['الاسم', 'الهاتف', 'الهاتف الثاني', 'البريد الإلكتروني', 'العنوان', 'تاريخ الإنشاء']]
            
            for customer in customers:
                data.append([
                    str(customer.name),
                    str(customer.phone) if hasattr(customer, 'phone') else '',
                    str(customer.phone2) if hasattr(customer, 'phone2') else '',
                    str(customer.email) if hasattr(customer, 'email') else '',
                    str(customer.address) if hasattr(customer, 'address') else '',
                    customer.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(customer, 'created_at') and customer.created_at else ''
                ])
            
            updated_rows = update_sheet(self.service, self.config.spreadsheet_id, 'العملاء', data)
            return {'status': 'success', 'message': f"تمت مزامنة {updated_rows} عميل"}
            
        except Exception as e:
            return {'status': 'error', 'message': f"خطأ في مزامنة العملاء: {str(e)}"}
    
    def _sync_orders(self) -> Dict[str, Any]:
        """مزامنة الطلبات"""
        try:
            Order = apps.get_model('orders', 'Order')
            orders = Order.objects.all()
            
            data = [['رقم الطلب', 'العميل', 'الحالة', 'المبلغ الإجمالي', 'تاريخ الطلب']]
            
            for order in orders:
                customer_name = str(order.customer.name) if hasattr(order, 'customer') and order.customer else ''
                data.append([
                    str(order.id),
                    customer_name,
                    str(order.status) if hasattr(order, 'status') else '',
                    str(order.total_amount) if hasattr(order, 'total_amount') else '',
                    order.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(order, 'created_at') and order.created_at else ''
                ])
            
            updated_rows = update_sheet(self.service, self.config.spreadsheet_id, 'الطلبات', data)
            return {'status': 'success', 'message': f"تمت مزامنة {updated_rows} طلب"}
            
        except Exception as e:
            return {'status': 'error', 'message': f"خطأ في مزامنة الطلبات: {str(e)}"}
    
    def _sync_products(self) -> Dict[str, Any]:
        """مزامنة المنتجات"""
        try:
            Product = apps.get_model('inventory', 'Product')
            products = Product.objects.all()
            
            data = [['الاسم', 'الكود', 'السعر', 'الكمية المتوفرة', 'الوحدة']]
            
            for product in products:
                data.append([
                    str(product.name) if hasattr(product, 'name') else '',
                    str(product.code) if hasattr(product, 'code') else '',
                    str(product.price) if hasattr(product, 'price') else '',
                    str(product.quantity) if hasattr(product, 'quantity') else '',
                    str(product.unit) if hasattr(product, 'unit') else ''
                ])
            
            updated_rows = update_sheet(self.service, self.config.spreadsheet_id, 'المنتجات', data)
            return {'status': 'success', 'message': f"تمت مزامنة {updated_rows} منتج"}
            
        except Exception as e:
            return {'status': 'error', 'message': f"خطأ في مزامنة المنتجات: {str(e)}"}
    
    def _sync_inspections(self) -> Dict[str, Any]:
        """مزامنة المعاينات"""
        try:
            Inspection = apps.get_model('inspections', 'Inspection')
            inspections = Inspection.objects.all()
            
            data = [['رقم المعاينة', 'العميل', 'تاريخ الطلب', 'تاريخ التنفيذ', 'الحالة', 'النتيجة']]
            
            for inspection in inspections:
                customer_name = str(inspection.customer.name) if hasattr(inspection, 'customer') and inspection.customer else ''
                data.append([
                    str(inspection.id),
                    customer_name,
                    inspection.request_date.strftime('%Y-%m-%d') if hasattr(inspection, 'request_date') and inspection.request_date else '',
                    inspection.scheduled_date.strftime('%Y-%m-%d') if hasattr(inspection, 'scheduled_date') and inspection.scheduled_date else '',
                    str(inspection.status) if hasattr(inspection, 'status') else '',
                    str(inspection.result) if hasattr(inspection, 'result') else ''
                ])
            
            updated_rows = update_sheet(self.service, self.config.spreadsheet_id, 'المعاينات', data)
            return {'status': 'success', 'message': f"تمت مزامنة {updated_rows} معاينة"}
            
        except Exception as e:
            return {'status': 'error', 'message': f"خطأ في مزامنة المعاينات: {str(e)}"}
    
    def _sync_settings(self) -> Dict[str, Any]:
        """مزامنة الإعدادات"""
        try:
            CompanyInfo = apps.get_model('accounts', 'CompanyInfo')
            company_info = CompanyInfo.objects.first()
            
            data = [['الإعداد', 'القيمة']]
            
            if company_info:
                data.extend([
                    ['اسم الشركة', str(company_info.name) if hasattr(company_info, 'name') else ''],
                    ['العنوان', str(company_info.address) if hasattr(company_info, 'address') else ''],
                    ['الهاتف', str(company_info.phone) if hasattr(company_info, 'phone') else ''],
                    ['البريد الإلكتروني', str(company_info.email) if hasattr(company_info, 'email') else ''],
                    ['الموقع الإلكتروني', str(company_info.website) if hasattr(company_info, 'website') else '']
                ])
            
            updated_rows = update_sheet(self.service, self.config.spreadsheet_id, 'إعدادات الشركة', data)
            return {'status': 'success', 'message': 'تمت مزامنة إعدادات الشركة'}
            
        except Exception as e:
            return {'status': 'error', 'message': f"خطأ في مزامنة الإعدادات: {str(e)}"}
    
    def _sync_branches(self) -> Dict[str, Any]:
        """مزامنة الفروع"""
        try:
            Branch = apps.get_model('accounts', 'Branch')
            branches = Branch.objects.all()
            
            data = [['الاسم', 'العنوان', 'الهاتف', 'المدير', 'نشط']]
            
            for branch in branches:
                manager_name = str(branch.manager.get_full_name()) if hasattr(branch, 'manager') and branch.manager else ''
                data.append([
                    str(branch.name) if hasattr(branch, 'name') else '',
                    str(branch.address) if hasattr(branch, 'address') else '',
                    str(branch.phone) if hasattr(branch, 'phone') else '',
                    manager_name,
                    'نعم' if getattr(branch, 'is_active', True) else 'لا'
                ])
            
            updated_rows = update_sheet(self.service, self.config.spreadsheet_id, 'الفروع', data)
            return {'status': 'success', 'message': f"تمت مزامنة {updated_rows} فرع"}
            
        except Exception as e:
            return {'status': 'error', 'message': f"خطأ في مزامنة الفروع: {str(e)}"}
    
    def _log_sync_results(self, results: Dict[str, Any]):
        """تسجيل نتائج المزامنة"""
        try:
            if not self.config:
                return
            
            status = 'success' if self.stats['failed_syncs'] == 0 else 'warning' if self.stats['successful_syncs'] > 0 else 'error'
            message = f"مزامنة مكتملة: {self.stats['successful_syncs']} نجح، {self.stats['failed_syncs']} فشل"
            
            GoogleSyncLog.objects.create(
                config=self.config,
                status=status,
                message=message,
                details={
                    'results': results,
                    'stats': self.stats
                }
            )
            
        except Exception as e:
            logger.error(f"خطأ في تسجيل نتائج المزامنة: {str(e)}")


def sync_with_google_sheets_enhanced(config_id: int = None, selected_tables: List[str] = None) -> Dict[str, Any]:
    """
    دالة مزامنة محسنة مع Google Sheets
    """
    try:
        config = None
        if config_id:
            config = GoogleSyncConfig.objects.get(id=config_id)
        
        service = GoogleSyncService(config)
        return service.sync_all_data(selected_tables)
        
    except Exception as e:
        logger.error(f"خطأ في المزامنة المحسنة: {str(e)}")
        return {'status': 'error', 'message': str(e)}