"""
خدمة المزامنة المتقدمة مع Google Sheets
Advanced Google Sheets Sync Service
"""

import logging
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django.conf import settings

from .google_sync_advanced import (
    GoogleSheetMapping, GoogleSyncTask, GoogleSyncConflict, GoogleSyncSchedule
)
from .google_sheets_import import GoogleSheetsImporter
from customers.models import Customer, CustomerCategory
from orders.models import Order
from orders.extended_models import ExtendedOrder
from inspections.models import Inspection
from installations.models import Installation, InstallationTeam
from accounts.models import Branch, Salesperson

logger = logging.getLogger(__name__)


class AdvancedSyncService:
    """خدمة المزامنة المتقدمة"""

    def __init__(self, mapping: GoogleSheetMapping):
        self.mapping = mapping
        self.importer = GoogleSheetsImporter()
        self.conflicts = []
        self.headers_cache = None  # Cache para los encabezados
        self.stats = {
            'total_rows': 0,
            'processed_rows': 0,
            'successful_rows': 0,
            'failed_rows': 0,
            'created_customers': 0,
            'updated_customers': 0,
            'created_orders': 0,
            'updated_orders': 0,
            'created_inspections': 0,
            'created_installations': 0,
            'errors': []
        }

    def sync_from_sheets(self, task: GoogleSyncTask = None) -> Dict[str, Any]:
        """
        تنفيذ المزامنة من Google Sheets باستخدام التعيينات المخصصة
        """
        print("=== SYNC_FROM_SHEETS CALLED ===", file=sys.stderr, flush=True)
        logger.info("=== SYNC_FROM_SHEETS STARTED ===")
        logger.info(f"Mapping: {self.mapping.name}, Sheet: {self.mapping.sheet_name}, Spreadsheet ID: {self.mapping.spreadsheet_id}")
        try:
            # تهيئة المستورد
            self.importer.initialize()

            # إنشاء مهمة إذا لم تكن موجودة
            if not task:
                task = GoogleSyncTask.objects.create(
                    mapping=self.mapping,
                    task_type='import',
                    created_by=None  # يمكن تحديد المستخدم لاحقاً
                )

            task.start_task()

            # جلب البيانات من Google Sheets
            sheet_data = self._get_sheet_data()
            if not sheet_data:
                error_msg = "No data returned from Google Sheets - sheet may be empty or not exist"
                logger.error(error_msg)
                task.fail_task(error_msg)
                return {'success': False, 'error': error_msg}

            # Log sheet data info
            logger.info(f"Sheet data retrieved - Rows: {len(sheet_data) if sheet_data else 0}")
            if sheet_data and len(sheet_data) > 0:
                logger.info(f"First row (headers): {sheet_data[0]}")
                if len(sheet_data) > 1:
                    logger.info(f"Sample data row: {sheet_data[1]}")

            # معالجة البيانات
            self.stats['total_rows'] = len(sheet_data) - self.mapping.header_row
            task.total_rows = self.stats['total_rows']
            task.save(update_fields=['total_rows'])

            # معالجة كل صف
            for row_index, row_data in enumerate(sheet_data[self.mapping.start_row - 1:],
                                               start=self.mapping.start_row):
                try:
                    self._process_row(row_data, row_index, task)
                    self.stats['processed_rows'] += 1
                    self.stats['successful_rows'] += 1

                    # تحديث تقدم المهمة
                    task.processed_rows = self.stats['processed_rows']
                    task.successful_rows = self.stats['successful_rows']
                    task.save(update_fields=['processed_rows', 'successful_rows'])

                except Exception as e:
                    logger.error(f"خطأ في معالجة الصف {row_index}: {str(e)}")
                    self.stats['failed_rows'] += 1
                    task.failed_rows = self.stats['failed_rows']
                    task.save(update_fields=['failed_rows'])

                    # إنشاء تعارض
                    self._create_conflict(
                        task, 'validation_error', 'unknown', row_index,
                        {}, dict(zip(self._get_headers(), row_data)),
                        f"خطأ في معالجة الصف: {str(e)}"
                    )
                    
                    # إضافة الخطأ إلى قائمة الأخطاء
                    self.stats['errors'].append(f"صف {row_index}: {str(e)}")

            # تحديث آخر صف تمت معالجته
            self.mapping.last_row_processed = self.stats['processed_rows'] + self.mapping.start_row - 1
            self.mapping.last_sync = timezone.now()
            self.mapping.save(update_fields=['last_row_processed', 'last_sync'])

            # إكمال المهمة
            task.complete_task(self.stats)

            # توحيد مفاتيح الإحصائيات مع السكريبت
            stats_out = dict(self.stats)
            stats_out['customers_created'] = self.stats.get('created_customers', 0)
            stats_out['customers_updated'] = self.stats.get('updated_customers', 0)
            stats_out['orders_created'] = self.stats.get('created_orders', 0)
            stats_out['orders_updated'] = self.stats.get('updated_orders', 0)

            return {
                'success': True,
                'stats': stats_out,
                'conflicts': len(self.conflicts),
                'task_id': task.id
            }

        except Exception as e:
            logger.error(f"خطأ في المزامنة: {str(e)}")
            if task:
                task.fail_task(str(e))
            return {'success': False, 'error': str(e)}

    def sync_to_sheets(self, task: GoogleSyncTask = None) -> Dict[str, Any]:
        """مزامنة البيانات من النظام إلى Google Sheets (المزامنة العكسية)"""
        try:
            if not self.mapping.enable_reverse_sync:
                return {'success': False, 'error': 'المزامنة العكسية غير مفعلة'}

            # تهيئة المستورد
            self.importer.initialize()

            # إنشاء مهمة إذا لم تكن موجودة
            if not task:
                task = GoogleSyncTask.objects.create(
                    mapping=self.mapping,
                    task_type='reverse_sync',
                    created_by=None
                )

            task.start_task()

            # جلب البيانات من النظام
            system_data = self._get_system_data()

            # تحديث Google Sheets
            self._update_sheets_data(system_data, task)

            task.complete_task({'updated_rows': len(system_data)})

            return {
                'success': True,
                'updated_rows': len(system_data),
                'task_id': task.id
            }

        except Exception as e:
            logger.error(f"خطأ في المزامنة العكسية: {str(e)}")
            if task:
                task.fail_task(str(e))
            return {'success': False, 'error': str(e)}

    def _get_sheet_data(self) -> List[List[str]]:
        """جلب البيانات من Google Sheets"""
        try:
            logger.info(f"Fetching sheet data for sheet: {self.mapping.sheet_name}, Spreadsheet ID: {self.mapping.spreadsheet_id}")
            
            # جلب البيانات من Google Sheets
            sheet_data = self.importer.get_sheet_data(self.mapping.sheet_name)
            
            if not sheet_data:
                logger.warning("No data returned from get_sheet_data()")
                return []
                
            logger.info(f"Retrieved {len(sheet_data)} rows of data from sheet")
            
            # تسجيل الصفوف الأولى فقط للتشخيص (بحد أقصى 3 صفوف)
            if len(sheet_data) > 0:
                logger.info(f"First row (headers): {sheet_data[0]}")
                if len(sheet_data) > 1:
                    logger.info(f"First data row: {sheet_data[1]}")
                
            return sheet_data
            
        except Exception as e:
            logger.error(f"خطأ في جلب البيانات من Google Sheets: {str(e)}")
            raise

    def _get_headers(self) -> List[str]:
        """جلب عناوين الأعمدة مع التخزين المؤقت لتحسين الأداء"""
        if self.headers_cache is not None:
            return self.headers_cache
            
        try:
            sheet_data = self.importer.get_sheet_data(self.mapping.sheet_name)
            if sheet_data and len(sheet_data) >= self.mapping.header_row:
                self.headers_cache = sheet_data[self.mapping.header_row - 1]
                return self.headers_cache
            return []
        except Exception as e:
            logger.error(f"خطأ في جلب العناوين: {str(e)}")
            return []

    def _process_row(self, row_data: List[str], row_index: int, task: GoogleSyncTask):
        """
        معالجة صف واحد من البيانات
        
        المعلمات:
            row_data: قائمة بقيم الصف
            row_index: رقم الصف في الجدول (يبدأ من 1)
            task: مهمة المزامنة الحالية
        """
        try:
            # تسجيل بيانات الصف للتصحيح
            logger.debug(f"[DEBUG] معالجة الصف {row_index}: {row_data}")
            
            # تخطي الصفوف الفارغة
            if not any(cell and str(cell).strip() for cell in row_data):
                logger.info(f"[INFO] تخطي الصف {row_index}: صف فارغ")
                return

            # تحويل البيانات إلى قاموس
            mapped_data = self._map_row_data(row_data)

            # Log sheet data info
            logger.info(f"Sheet data retrieved - Rows: {len(sheet_data) if sheet_data else 0}")
            if sheet_data and len(sheet_data) > 0:
                logger.info(f"First row (headers): {sheet_data[0]}")
                if len(sheet_data) > 1:
                    logger.info(f"Sample data row: {sheet_data[1]}")
            
            # معالجة البيانات باستخدام التعيينات المخصصة
            logger.info("Starting to process custom data...")
            result = self.process_custom_data(sheet_data, task)
            logger.info(f"Custom data processing completed. Result: {result}")

            # معالجة العميل
            customer = self._process_customer(mapped_data, row_index, task)
            if not customer:
                logger.info(f"[INFO] تخطي الصف {row_index}: لم يتم معالجة العميل")
                return

            # معالجة الطلب
            order = self._process_order(mapped_data, customer, row_index, task)
            if not order and self.mapping.auto_create_orders:
                logger.info(f"[INFO] تخطي الصف {row_index}: لم يتم معالجة الطلب")
                return

            # معالجة المعاينة
            if self.mapping.auto_create_inspections and order:
                inspection = self._process_inspection(mapped_data, customer, order, row_index, task)
                if not inspection and self.mapping.require_inspection:
                    logger.info(f"[INFO] تخطي الصف {row_index}: لم يتم معالجة المعاينة")
                    return

            # معالجة التركيب
            if self.mapping.auto_create_installations and order:
                installation = self._process_installation(mapped_data, customer, order, row_index, task)
                if not installation and self.mapping.require_installation:
                    logger.info(f"[INFO] تخطي الصف {row_index}: لم يتم معالجة التركيب")
                    return

            logger.debug(f"[DEBUG] تمت معالجة الصف {row_index} بنجاح")

        except Exception as e:
            error_msg = f"خطأ في معالجة الصف {row_index}: {str(e)}"
            logger.error(error_msg)
            logger.exception(e)
            self.stats['failed_rows'] += 1
            
            # تسجيل الخطأ في المهمة إذا كانت متوفرة
            if hasattr(task, 'add_error'):
                task.add_error(f"خطأ في الصف {row_index}: {str(e)}")
            
            # إعادة رفع الاستثناء إذا كنا في وضع التصحيح
            if settings.DEBUG:
                raise

    def _map_row_data(self, row_data: List[str]) -> Dict[str, str]:
        """تحويل بيانات الصف إلى قاموس مع التعيينات"""
        mapped_data = {}
        # جلب العناوين من الشيت
        headers = self._get_headers()
        
        # تحسين الأداء: تخزين column_mappings مؤقتًا
        column_mappings = self.mapping.column_mappings
        
        for col_index, value in enumerate(row_data):
            # اسم العمود من الشيت (قد يكون فارغاً)
            col_name = headers[col_index] if col_index < len(headers) else None
            
            # جرب المطابقة بالاسم بعد strip
            field_type = None
            if col_name:
                # تحسين الأداء: البحث المباشر في القاموس بدلاً من استدعاء دالة
                col_name_stripped = col_name.strip()
                field_type = column_mappings.get(col_name_stripped)
            
            # إذا لم يوجد، جرب المطابقة بالرقم
            if not field_type:
                # تحسين الأداء: البحث المباشر في القاموس بدلاً من استدعاء دالة
                field_type = column_mappings.get(str(col_index))
            
            if field_type and field_type != 'ignore':
                mapped_data[field_type] = value.strip() if value else ''
                
        return mapped_data

    def _process_customer(self, mapped_data: Dict[str, str], row_index: int,
                         task: GoogleSyncTask) -> Optional[Customer]:
        """معالجة بيانات العميل"""
        try:
            customer_name = mapped_data.get('customer_name', '').strip()
            if not customer_name:
                return None

            customer_phone = mapped_data.get('customer_phone', '').strip()
            customer_email = mapped_data.get('customer_email', '').strip()

            # البحث عن العميل الموجود
            customer = None
            if customer_phone:
                customer = Customer.objects.filter(phone=customer_phone).first()

            if not customer and customer_email:
                customer = Customer.objects.filter(email=customer_email).first()

            if not customer and customer_name:
                customer = Customer.objects.filter(name=customer_name).first()

            if customer:
                # إذا وُجد عميل بنفس الاسم والهاتف، يتم التحديث فقط
                if self.mapping.update_existing_customers:
                    logger.debug(f"[DEBUG] تحديث بيانات العميل الموجود: {customer_name} (ID: {customer.id})")
                    self._update_customer(customer, mapped_data)
                    self.stats['updated_customers'] += 1
            else:
                if self.mapping.auto_create_customers:
                    customer = self._create_customer(mapped_data)
                    self.stats['created_customers'] += 1

            return customer

        except Exception as e:
            error_msg = f"خطأ في معالجة العميل في الصف {row_index}: {str(e)}"
            logger.error(error_msg)
            logger.exception(e)
            raise

    def _create_customer(self, mapped_data: Dict[str, str]) -> Customer:
        """إنشاء عميل جديد"""
        customer_data = {
            'name': mapped_data.get('customer_name', ''),
            'phone': mapped_data.get('customer_phone', ''),
            'phone2': mapped_data.get('customer_phone2', ''),
            'email': mapped_data.get('customer_email', ''),
            'address': mapped_data.get('customer_address', ''),
        }

        # تحديد الفرع
        branch_name = mapped_data.get('branch', '')
        if branch_name:
            branch = Branch.objects.filter(name__icontains=branch_name).first()
            if branch:
                customer_data['branch'] = branch

        # إنشاء كود العميل تلقائياً
        customer_data['code'] = self._generate_customer_code()

        return Customer.objects.create(**customer_data)

    def _update_customer(self, customer: Customer, mapped_data: Dict[str, str]):
        """تحديث بيانات العميل"""
        updated = False

        # تحديث الحقول إذا كانت فارغة أو مختلفة
        if mapped_data.get('customer_phone2') and not customer.phone2:
            customer.phone2 = mapped_data['customer_phone2']
            updated = True

        if mapped_data.get('customer_email') and not customer.email:
            customer.email = mapped_data['customer_email']
            updated = True

        if mapped_data.get('customer_address') and customer.address != mapped_data['customer_address']:
            customer.address = mapped_data['customer_address']
            updated = True

        if updated:
            customer.save()

    def _process_order(self, mapped_data: Dict[str, str], customer: Optional[Customer],
                      row_index: int, task: GoogleSyncTask) -> Optional[Order]:
        """معالجة بيانات الطلب"""
        try:
            if not customer or not self.mapping.auto_create_orders:
                return None

            order_number = mapped_data.get('order_number', '').strip()
            
            # البحث عن الطلب الموجود
            order = None
            if order_number:
                order = Order.objects.filter(order_number=order_number).first()

            # إنشاء أو تحديث الطلب
            if order:
                if self.mapping.update_existing_orders:
                    self._update_order(order, mapped_data)
                    self.stats['updated_orders'] += 1
            else:
                order = self._create_order(customer, mapped_data)
                self.stats['created_orders'] += 1

            return order

        except Exception as e:
            logger.error(f"خطأ في معالجة الطلب في الصف {row_index}: {str(e)}")
            raise

    def _create_order(self, customer: Customer, mapped_data: Dict[str, str]) -> Order:
        """إنشاء طلب جديد"""
        order_data = {
            'customer': customer,
            'status': mapped_data.get('order_status', 'new'),
        }

        # لا نمرر order_number ليتم توليده تلقائيًا حسب النظام في نموذج Order
        # إذا كان هناك منطق خاص لقبول رقم الطلب من Google Sheets، يمكن تعديله هنا

        # إنشاء الطلب
        order = Order.objects.create(**order_data)
        return order

    def _update_order(self, order: Order, mapped_data: Dict[str, str]) -> Order:
        """تحديث بيانات الطلب"""
        # تحديث البيانات الأساسية
        for field, value in mapped_data.items():
            if field.startswith('order_') and hasattr(order, field.replace('order_', '')):
                setattr(order, field.replace('order_', ''), value)
        
        # حفظ التغييرات
        order.save()
        return order

    def _process_inspection(self, mapped_data: Dict[str, str], customer: Customer,
                           order: Order, row_index: int, task: GoogleSyncTask) -> Optional[Inspection]:
        """معالجة بيانات المعاينة: لا تُنشأ إلا إذا وُجد تاريخ صالح، مع معالجة جميع التنسيقات"""
        try:
            if not customer or not order:
                fail_reason = f"لم يتم إنشاء المعاينة للصف {row_index}: لا يوجد عميل أو طلب."
                logger.error(fail_reason)
                self.stats['errors'].append(fail_reason)
                return None

            # جلب تاريخ المعاينة من البيانات
            inspection_date_str = mapped_data.get('inspection_date', '').strip()
            if not inspection_date_str:
                fail_reason = f"لم يتم إنشاء المعاينة للصف {row_index}: لا يوجد تاريخ معاينة."
                logger.info(fail_reason)
                self.stats['errors'].append(fail_reason)
                return None

            # محاولة تحويل التاريخ باستخدام dateutil
            try:
                from dateutil import parser as date_parser
                scheduled_date = date_parser.parse(inspection_date_str, dayfirst=True).date()
            except Exception:
                fail_reason = f"لم يتم إنشاء المعاينة للصف {row_index}: تاريخ المعاينة غير صالح [{inspection_date_str}]."
                logger.info(fail_reason)
                self.stats['errors'].append(fail_reason)
                return None

            # التحقق من وجود معاينة سابقة
            inspection = Inspection.objects.filter(order=order).first()
            if inspection:
                return inspection

            from django.utils import timezone
            inspection = Inspection.objects.create(
                customer=customer,
                order=order,
                status='pending',
                request_date=timezone.now().date(),
                scheduled_date=scheduled_date
            )

            self.stats['created_inspections'] += 1
            return inspection

        except Exception as e:
            fail_reason = f"خطأ في معالجة المعاينة في الصف {row_index}: {str(e)}"
            logger.error(fail_reason)
            self.stats['errors'].append(fail_reason)
            return None

    def _process_installation(self, mapped_data: Dict[str, str], customer: Customer,
                             order: Order, row_index: int, task: GoogleSyncTask) -> Optional[Installation]:
        """معالجة بيانات التركيب"""
        try:
            if not customer or not order:
                return None

            # التحقق من وجود تركيب سابق
            installation = Installation.objects.filter(order=order).first()
            if installation:
                return installation

            # إنشاء تركيب جديد
            from django.utils import timezone
            
            # Establecer la fecha de solicitud como la fecha actual si no está disponible
            installation = Installation.objects.create(
                customer=customer,
                order=order,
                status='pending',
                request_date=timezone.now().date()  # Agregar la fecha de solicitud requerida
            )
            
            # Si hay una fecha de instalación en los datos mapeados, actualizarla
            installation_date = mapped_data.get('installation_date', '').strip()
            if installation_date:
                try:
                    from datetime import datetime
                    scheduled_date = datetime.strptime(installation_date, '%d-%m-%Y').date()
                    installation.scheduled_date = scheduled_date
                    installation.save(update_fields=['scheduled_date'])
                except ValueError:
                    pass
                    
            self.stats['created_installations'] += 1
            return installation

        except Exception as e:
            logger.error(f"خطأ في معالجة التركيب في الصف {row_index}: {str(e)}")
            return None

    def _create_conflict(self, task: GoogleSyncTask, conflict_type: str, field_name: str,
                        row_index: int, system_data: Dict[str, Any], sheet_data: Dict[str, Any],
                        description: str) -> GoogleSyncConflict:
        """إنشاء تعارض"""
        conflict = GoogleSyncConflict.objects.create(
            task=task,
            conflict_type=conflict_type,
            field_name=field_name,
            row_index=row_index,
            system_data=system_data,
            sheet_data=sheet_data,
            description=description,
        )
        self.conflicts.append(conflict)
        return conflict

    def _get_system_data(self) -> List[List[str]]:
        """جلب بيانات النظام للمزامنة العكسية"""
        # هذه الدالة تحتاج إلى تنفيذ حسب متطلبات المزامنة العكسية
        return []

    def _update_sheets_data(self, system_data: List[Dict[str, Any]], task: GoogleSyncTask):
        """تحديث بيانات Google Sheets"""
        # هذه الدالة ستحتاج تطوير أكثر حسب متطلبات المزامنة العكسية
        pass


class SyncScheduler:
    """مجدول المزامنة التلقائية"""

    @staticmethod
    def run_scheduled_syncs():
        """تشغيل المزامنة المجدولة باستخدام نفس منطق السكريبت"""
        try:
            # البحث عن المزامنات المستحقة
            due_schedules = GoogleSyncSchedule.objects.filter(
                is_active=True,
                next_run__lte=timezone.now()
            )

            for schedule in due_schedules:
                try:
                    # جلب التعيين
                    mapping = schedule.mapping
                    
                    # إنشاء مستخدم النظام للمهمة المجدولة
                    from accounts.models import User
                    system_user = User.objects.filter(is_superuser=True).first()
                    
                    # إنشاء مهمة جديدة
                    task = GoogleSyncTask.objects.create(
                        mapping=mapping,
                        task_type='import',
                        created_by=system_user,
                        is_scheduled=True
                    )
                    
                    # تشغيل المهمة
                    task.start_task()
                    
                    # تنفيذ المزامنة
                    service = AdvancedSyncService(mapping)
                    result = service.sync_from_sheets(task)
                    
                    # معالجة النتيجة
                    if result['success']:
                        task.mark_completed(result)
                        stats = result['stats']
                        logger.info(f"تمت المزامنة المجدولة بنجاح: {mapping.name}")
                        logger.info(f"إحصائيات: إجمالي الصفوف: {stats['total_rows']}, المعالجة: {stats['processed_rows']}")
                    else:
                        task.mark_failed(result.get('error', 'خطأ غير معروف'))
                        logger.error(f"فشلت المزامنة المجدولة: {mapping.name} - {result.get('error')}")
                    
                    # تسجيل النتيجة في الجدولة
                    schedule.record_run(success=result.get('success', False))

                except Exception as e:
                    logger.error(f"خطأ في تشغيل المزامنة المجدولة {schedule.mapping.name}: {str(e)}")
                    schedule.record_run(success=False)

        except Exception as e:
            logger.error(f"خطأ في تشغيل المزامنة المجدولة: {str(e)}")