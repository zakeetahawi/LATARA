"""
خدمة المزامنة المتقدمة مع Google Sheets
Advanced Google Sheets Sync Service
"""

import logging
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from django.utils import timezone
from django.db import transaction, IntegrityError
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
        self.stats = {
            'total_rows': 0,
            'processed_rows': 0,
            'successful_rows': 0,
            'failed_rows': 0,
            'customers_created': 0,
            'customers_updated': 0,
            'orders_created': 0,
            'orders_updated': 0,
            'inspections_created': 0,
            'installations_created': 0,
            'errors': [],
        }

    def sync_from_sheets(self, task: GoogleSyncTask = None) -> Dict[str, Any]:
        """
        تنفيذ المزامنة من Google Sheets باستخدام التعيينات المخصصة
        تسريع التنفيذ عبر:
        - تقليل عمليات الحفظ في قاعدة البيانات (batching)
        - تقليل عمليات تحديث المهام أثناء الحلقة
        - تعطيل إنشاء التعارضات أثناء المزامنة السريعة
        - تقليل عمليات جلب الحقول (headers) المتكررة
        """
        start_time = time.perf_counter()
        try:
            self.importer.initialize()
            if not task:
                task = GoogleSyncTask.objects.create(
                    mapping=self.mapping,
                    task_type='import',
                    created_by=None
                )
            task.start_task()
            sheet_data = self._get_sheet_data()
            if not sheet_data:
                error_msg = "لا توجد بيانات في الجدول"
                logger.error(error_msg)
                task.fail_task(error_msg)
                return {'success': False, 'error': error_msg}

            # جلب العناوين مرة واحدة فقط
            headers = self._get_headers()
            data_start = max(self.mapping.header_row, self.mapping.start_row)
            data_rows = sheet_data[data_start:]
            self.stats['total_rows'] = len(data_rows)
            task.total_rows = self.stats['total_rows']
            task.save(update_fields=['total_rows'])

            customer_cache = {}
            imported_orders = set()
            imported_inspections = set()
            updated_orders = 0

            for i, row_data in enumerate(data_rows):
                sheet_row_number = data_start + 1 + i  # 1-based sheet row number
                try:
                    mapped_data = self._map_row_data(row_data, headers)
                    if not mapped_data.get('branch') and self.mapping.default_branch:
                        mapped_data['branch'] = self.mapping.default_branch.name
                    if not mapped_data.get('customer_category') and self.mapping.default_customer_category:
                        mapped_data['customer_category'] = self.mapping.default_customer_category.name

                    # معالجة العميل (دائمًا لكل صف)
                    customer_key = (mapped_data.get('customer_name', '').strip(), mapped_data.get('customer_phone', '').strip())
                    customer = customer_cache.get(customer_key)
                    if not customer:
                        customer = self._process_customer(mapped_data, sheet_row_number, task)
                        customer_cache[customer_key] = customer

                    # كل صف = طلب واحد (إجباري حسب المتطلبات الجديدة)
                    order_number = mapped_data.get('order_number', '').strip()
                    invoice_number = mapped_data.get('invoice_number', '').strip()
                    contract_number = mapped_data.get('contract_number', '').strip()
                    customer_name = mapped_data.get('customer_name', '').strip()
                    customer_phone = mapped_data.get('customer_phone', '').strip()

                    # التحقق من وجود رقم الفاتورة (إلزامي لجميع الطلبات)
                    if not invoice_number:
                        self.stats['errors'].append(f"الصف {sheet_row_number}: رقم الفاتورة مطلوب لجميع الطلبات")
                        continue

                    # مفتاح الطلب لمنع التكرار (بناء على رقم الفاتورة بشكل أساسي)
                    order_key = f"invoice_{invoice_number}"
                    if order_key in imported_orders:
                        self.stats['warnings'].append(f"الصف {sheet_row_number}: طلب مكرر بنفس رقم الفاتورة {invoice_number}")
                        continue

                    # البحث عن الطلب الموجود بناء على رقم الفاتورة
                    order = Order.objects.filter(invoice_number=invoice_number).first()

                    if not order:
                        # إنشاء طلب جديد (كل صف = طلب)
                        order = self._process_order(mapped_data, customer, sheet_row_number, task)
                        if order:
                            imported_orders.add(order_key)
                            self.stats['orders_created'] += 1
                            logger.info(f"تم إنشاء طلب جديد: رقم الفاتورة {invoice_number}")
                    else:
                        # طلب موجود - تحديث إذا كان مفعل
                        if self.mapping.update_existing:
                            self._update_order(order, mapped_data, customer)
                            self.stats['orders_updated'] += 1
                        imported_orders.add(order_key)

                    # المعاينة: إنشاء معاينة إذا وُجد تاريخ معاينة (حسب المتطلبات الجديدة)
                    inspection_date = mapped_data.get('inspection_date', '').strip()
                    if inspection_date and self.mapping.auto_create_inspections and order:
                        # مفتاح المعاينة لمنع التكرار
                        inspection_key = f"order_{order.id}_date_{inspection_date}"
                        if inspection_key not in imported_inspections:
                            # التحقق من عدم وجود معاينة لنفس الطلب ونفس التاريخ
                            try:
                                parsed_date = datetime.strptime(inspection_date, '%Y-%m-%d').date()
                                existing_inspection = Inspection.objects.filter(
                                    order=order, 
                                    scheduled_date=parsed_date
                                ).first()
                                
                                if not existing_inspection:
                                    inspection = self._process_inspection(mapped_data, customer, order, sheet_row_number, task)
                                    if inspection:
                                        imported_inspections.add(inspection_key)
                                        self.stats['inspections_created'] += 1
                                        logger.info(f"تم إنشاء معاينة جديدة للطلب رقم {invoice_number} بتاريخ {inspection_date}")
                            except ValueError:
                                self.stats['warnings'].append(f"الصف {sheet_row_number}: تنسيق تاريخ المعاينة غير صحيح {inspection_date}")

                    if self.mapping.auto_create_installations and order:
                        self._process_installation(mapped_data, customer, order, sheet_row_number, task)

                    self.stats['processed_rows'] += 1
                    self.stats['successful_rows'] += 1

                except Exception as e:
                    self.stats['failed_rows'] += 1
                    self.stats['errors'].append(f"خطأ في الصف {sheet_row_number}: {str(e)}")

            self.mapping.last_row_processed = self.stats['processed_rows'] + self.mapping.start_row - 1
            self.mapping.last_sync = timezone.now()
            self.mapping.save(update_fields=['last_row_processed', 'last_sync'])
            task.processed_rows = self.stats['processed_rows']
            task.successful_rows = self.stats['successful_rows']
            task.failed_rows = self.stats['failed_rows']
            task.save(update_fields=['processed_rows', 'successful_rows', 'failed_rows'])
            task.complete_task(self.stats)
            elapsed = time.perf_counter() - start_time
            self.stats['elapsed_seconds'] = round(elapsed, 3)

            # رسالة تلخيصية في الترمنال
            print("="*40)
            print("نتيجة المزامنة:")
            print(f"عدد الطلبات المستوردة أو المحدثة: {len(imported_orders)}")
            print(f"عدد المعاينات المستوردة: {len(imported_inspections)}")
            print(f"عدد الأخطاء: {self.stats['failed_rows']}")
            print(f"عدد الطلبات المحدثة: {updated_orders}")
            print("="*40)

            return {
                'success': True,
                'stats': self.stats,
                'conflicts': 0,
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

            self.importer.initialize()
            if not task:
                task = GoogleSyncTask.objects.create(
                    mapping=self.mapping,
                    task_type='reverse_sync',
                    created_by=None
                )
            task.start_task()
            system_data = self._get_system_data()
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
            return self.importer.get_sheet_data(self.mapping.sheet_name)
        except Exception as e:
            logger.error(f"خطأ في جلب البيانات من Google Sheets: {str(e)}", exc_info=True)
            raise

    def _get_headers(self) -> List[str]:
        """جلب عناوين الأعمدة"""
        try:
            sheet_data = self.importer.get_sheet_data(self.mapping.sheet_name)
            if sheet_data and len(sheet_data) >= self.mapping.header_row:
                return sheet_data[self.mapping.header_row - 1]
            return []
        except Exception as e:
            logger.error(f"خطأ في جلب العناوين: {str(e)}")
            return []

    def _map_row_data(self, row_data: List[str], headers: list) -> Dict[str, str]:
        """تحويل بيانات الصف إلى قاموس مع التعيينات (headers cached)"""
        mapped_data = {}
        if len(row_data) != len(headers):
            logger.warning(
                f"Length mismatch: row_data has {len(row_data)} elements, headers has {len(headers)} elements."
            )
        for col_index, value in enumerate(row_data):
            col_name = headers[col_index] if col_index < len(headers) else None
            field_type = None
            if col_name:
                field_type = self.mapping.get_column_mapping(col_name.strip())
            if not field_type:
                field_type = self.mapping.get_column_mapping(col_index)
            if field_type and field_type != 'ignore':
                if field_type in mapped_data:
                    logger.warning(f"Duplicate field_type '{field_type}' in row mapping. Previous value will be overwritten.")
                mapped_data[field_type] = value.strip() if value else ''
        return mapped_data

    def _process_customer(self, mapped_data: Dict[str, str], row_index: int, task: GoogleSyncTask) -> Optional[Customer]:
        """معالجة بيانات العميل"""
        try:
            customer_name = mapped_data.get('customer_name', '').strip()
            if not customer_name:
                return None
            customer_phone = mapped_data.get('customer_phone', '').strip()
            customer_email = mapped_data.get('customer_email', '').strip()
            customer = None
            if customer_phone:
                customer = Customer.objects.filter(phone=customer_phone).first()
            if not customer and customer_email:
                customer = Customer.objects.filter(email=customer_email).first()
            if not customer and customer_name:
                customer = Customer.objects.filter(name=customer_name).first()
            if customer:
                if self.mapping.update_existing_customers:
                    self._update_customer(customer, mapped_data)
                    self.stats['customers_updated'] += 1
            else:
                if self.mapping.auto_create_customers:
                    customer = self._create_customer(mapped_data)
                    self.stats['customers_created'] += 1
            return customer
        except Exception as e:
            self.stats['errors'].append(f"خطأ في معالجة العميل في الصف {row_index}: {str(e)}")
            raise

    def _create_customer(self, mapped_data: Dict[str, str]) -> Customer:
        """إنشاء عميل جديد باتباع نمط التكويد الموجود في النظام (لوحة التحكم)"""
        customer_data = {
            'name': mapped_data.get('customer_name', ''),
            'phone': mapped_data.get('customer_phone', ''),
            'phone2': mapped_data.get('customer_phone2', ''),
            'email': mapped_data.get('customer_email', ''),
            'address': mapped_data.get('customer_address', ''),
        }
        if self.mapping.default_customer_category:
            customer_data['category'] = self.mapping.default_customer_category
        if self.mapping.default_customer_type:
            customer_data['customer_type'] = self.mapping.default_customer_type
        if self.mapping.default_branch:
            customer_data['branch'] = self.mapping.default_branch

        # إذا كان هناك دالة أو خاصية في الموديل Customer لتوليد الكود، استخدمها
        if hasattr(Customer, "generate_code") and callable(getattr(Customer, "generate_code")):
            customer_data['code'] = Customer.generate_code()

        try:
            return Customer.objects.create(**customer_data)
        except IntegrityError as e:
            raise Exception(f"فشل إنشاء عميل جديد: {str(e)}")

    def _update_customer(self, customer: Customer, mapped_data: Dict[str, str]):
        updated = False
        if mapped_data.get('customer_phone2'):
            new_phone2 = mapped_data['customer_phone2'].strip()
            current_phone2 = (customer.phone2 or '').strip()
            if new_phone2 and new_phone2 != current_phone2:
                customer.phone2 = new_phone2
                updated = True
        if mapped_data.get('customer_email') and mapped_data['customer_email'].strip() != (customer.email or '').strip():
            customer.email = mapped_data['customer_email'].strip()
            updated = True
        if mapped_data.get('customer_address') and mapped_data['customer_address'].strip() != (customer.address or '').strip():
            customer.address = mapped_data['customer_address'].strip()
            updated = True
        if updated:
            customer.save()

    def _process_order(self, mapped_data: Dict[str, str], customer: Customer, row_index: int, task: GoogleSyncTask) -> Optional[Order]:
        """معالجة بيانات الطلب"""
        try:
            if not customer:
                return None
            order_number = mapped_data.get('order_number', '').strip()
            invoice_number = mapped_data.get('invoice_number', '').strip()
            order = None
            if order_number:
                order = Order.objects.filter(order_number=order_number).first()
            elif invoice_number:
                order = Order.objects.filter(invoice_number=invoice_number).first()
            if order:
                if self.mapping.update_existing_orders:
                    self._update_order(order, mapped_data, customer)
                    self.stats['orders_updated'] += 1
            else:
                if self.mapping.auto_create_orders:
                    order = self._create_order(mapped_data, customer)
                    self.stats['orders_created'] += 1
            return order
        except Exception as e:
            self.stats['errors'].append(f"خطأ في معالجة الطلب في الصف {row_index}: {str(e)}")
            raise

    def _create_order(self, mapped_data: Dict[str, str], customer: Customer) -> Order:
        """إنشاء طلب جديد باتباع نمط التكويد الموجود في النظام (لوحة التحكم)"""
        order_data = {
            'customer': customer,
            'invoice_number': mapped_data.get('invoice_number', ''),
            'contract_number': mapped_data.get('contract_number', ''),
            'notes': mapped_data.get('notes', ''),
            'delivery_address': mapped_data.get('delivery_address', ''),
        }
        if self.mapping.default_branch:
            order_data['branch'] = self.mapping.default_branch

        tracking_status = mapped_data.get('tracking_status', '')
        if tracking_status:
            status_mapping = {
                'قيد الانتظار': 'pending',
                'قيد المعالجة': 'processing',
                'في المستودع': 'warehouse',
                'في المصنع': 'factory',
                'قيد القص': 'cutting',
                'جاهز للتسليم': 'ready',
                'تم التسليم': 'delivered',
            }
            order_data['tracking_status'] = status_mapping.get(tracking_status, 'pending')
        try:
            if mapped_data.get('total_amount'):
                order_data['total_amount'] = float(mapped_data['total_amount'])
        except (ValueError, TypeError):
            pass
        try:
            if mapped_data.get('paid_amount'):
                order_data['paid_amount'] = float(mapped_data['paid_amount'])
        except (ValueError, TypeError):
            pass
        delivery_type = mapped_data.get('delivery_type', '')
        if delivery_type:
            delivery_mapping = {
                'توصيل للمنزل': 'home',
                'استلام من الفرع': 'branch',
            }
            order_data['delivery_type'] = delivery_mapping.get(delivery_type, 'branch')
        salesperson_name = mapped_data.get('salesperson', '')
        if salesperson_name:
            salesperson = Salesperson.objects.filter(name__icontains=salesperson_name).first()
            if salesperson:
                order_data['salesperson'] = salesperson

        if hasattr(Order, "generate_order_number") and callable(getattr(Order, "generate_order_number")):
            order_data['order_number'] = Order.generate_order_number()

        try:
            return Order.objects.create(**order_data)
        except IntegrityError as e:
            raise Exception(f"فشل إنشاء طلب جديد: {str(e)}")

    def _update_order(self, order: Order, mapped_data: Dict[str, str], customer: Customer):
        updated = False
        tracking_status = mapped_data.get('tracking_status', '')
        if tracking_status:
            status_mapping = {
                'قيد الانتظار': 'pending',
                'قيد المعالجة': 'processing',
                'في المستودع': 'warehouse',
                'في المصنع': 'factory',
                'قيد القص': 'cutting',
                'جاهز للتسليم': 'ready',
                'تم التسليم': 'delivered',
            }
            new_status = status_mapping.get(tracking_status, order.tracking_status)
            if new_status != order.tracking_status:
                order.tracking_status = new_status
                updated = True
        try:
            total_amount = mapped_data.get('total_amount')
            if total_amount and float(total_amount) != order.total_amount:
                order.total_amount = float(total_amount)
                updated = True
        except (ValueError, TypeError):
            pass
        try:
            paid_amount = mapped_data.get('paid_amount')
            if paid_amount and float(paid_amount) != order.paid_amount:
                order.paid_amount = float(paid_amount)
                updated = True
        except (ValueError, TypeError):
            pass
        notes = mapped_data.get('notes', '')
        if notes and notes != order.notes:
            order.notes = notes
            updated = True
        if updated:
            order.save()

    def _process_inspection(self, mapped_data: Dict[str, str], customer: Customer, order: Order, row_index: int, task: GoogleSyncTask):
        """معالجة بيانات المعاينة باتباع نمط التكويد الموجود في النظام (لوحة التحكم)"""
        try:
            inspection_data = {
                'customer': customer,
                'order': order,
                'branch': customer.branch or order.branch,
                'request_date': timezone.now().date(),
                'scheduled_date': timezone.now().date() + timedelta(days=1),
                'notes': mapped_data.get('notes', ''),
                'contract_number': mapped_data.get('contract_number', ''),  # إضافة رقم العقد
            }
            inspection_date = mapped_data.get('inspection_date', '')
            if inspection_date:
                try:
                    parsed_date = datetime.strptime(inspection_date, '%Y-%m-%d').date()
                    inspection_data['scheduled_date'] = parsed_date
                except ValueError:
                    pass
            inspection_result = mapped_data.get('inspection_result', '')
            if inspection_result:
                result_mapping = {
                    'مقبول': 'approved',
                    'مرفوض': 'rejected',
                    'يحتاج مراجعة': 'pending',
                }
                inspection_data['result'] = result_mapping.get(inspection_result, 'pending')
            windows_count = mapped_data.get('windows_count', '')
            if windows_count:
                try:
                    inspection_data['windows_count'] = int(windows_count)
                except (ValueError, TypeError):
                    pass

            if hasattr(Inspection, "generate_code") and callable(getattr(Inspection, "generate_code")):
                inspection_data['code'] = Inspection.generate_code()

            inspection = Inspection.objects.create(**inspection_data)
            self.stats['inspections_created'] += 1
            return inspection
        except Exception as e:
            self.stats['errors'].append(f"خطأ في معالجة المعاينة في الصف {row_index}: {str(e)}")
            raise

    def _process_installation(self, mapped_data: Dict[str, str], customer: Customer, order: Order, row_index: int, task: GoogleSyncTask):
        """معالجة بيانات التركيب"""
        try:
            existing_installation = Installation.objects.filter(order=order).first()
            if existing_installation:
                return existing_installation
            installation_data = {
                'order': order,
                'scheduled_date': timezone.now().date() + timedelta(days=7),
                'notes': mapped_data.get('notes', ''),
            }
            installation_status = mapped_data.get('installation_status', '')
            if installation_status:
                status_mapping = {
                    'قيد الانتظار': 'pending',
                    'مجدول': 'scheduled',
                    'جاري التنفيذ': 'in_progress',
                    'مكتمل': 'completed',
                    'ملغي': 'cancelled',
                }
                installation_data['status'] = status_mapping.get(installation_status, 'pending')
            if customer.branch:
                team = InstallationTeam.objects.filter(branch=customer.branch, is_active=True).first()
                if team:
                    installation_data['team'] = team
            installation = Installation.objects.create(**installation_data)
            self.stats['installations_created'] += 1
            return installation
        except Exception as e:
            self.stats['errors'].append(f"خطأ في معالجة التركيب في الصف {row_index}: {str(e)}")
            raise

    def _create_conflict(self, task: GoogleSyncTask, conflict_type: str,
                        record_type: str, sheet_row: int, system_data: Dict,
                        sheet_data: Dict, description: str):
        conflict = GoogleSyncConflict.objects.create(
            task=task,
            conflict_type=conflict_type,
            record_type=record_type,
            sheet_row=sheet_row,
            system_data=system_data,
            sheet_data=sheet_data,
            conflict_description=description
        )
        self.conflicts.append(conflict)
        return conflict

    def _get_system_data(self) -> List[Dict[str, Any]]:
        raise NotImplementedError("Reverse sync system data retrieval is not yet implemented.")

    def _update_sheets_data(self, system_data: List[Dict[str, Any]], task: GoogleSyncTask):
        pass


class SyncScheduler:
    """مجدول المزامنة التلقائية"""

    @staticmethod
    def run_scheduled_syncs():
        """تشغيل المزامنة المجدولة"""
        try:
            due_schedules = GoogleSyncSchedule.objects.filter(
                is_active=True,
                next_run__lte=timezone.now()
            )
            for schedule in due_schedules:
                try:
                    sync_service = AdvancedSyncService(schedule.mapping)
                    result = sync_service.sync_from_sheets()
                    schedule.record_run(success=result.get('success', False))
                    logger.info(f"تم تشغيل المزامنة المجدولة: {schedule.mapping.name}")
                except Exception as e:
                    logger.error(f"خطأ في تشغيل المزامنة المجدولة {schedule.mapping.name}: {str(e)}")
                    schedule.record_run(success=False)
        except Exception as e:
            logger.error(f"خطأ في مجدول المزامنة: {str(e)}")
            