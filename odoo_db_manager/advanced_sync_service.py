"""
خدمة المزامنة المتقدمة مع Google Sheets
Advanced Google Sheets Sync Service
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError

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
            'created_customers': 0,
            'updated_customers': 0,
            'created_orders': 0,
            'updated_orders': 0,
            'created_inspections': 0,
            'created_installations': 0,
        }

    def sync_from_sheets(self, task: GoogleSyncTask = None) -> Dict[str, Any]:
        """
        تنفيذ المزامنة من Google Sheets باستخدام التعيينات المخصصة
        """
        logger.info(f"SYNC LOG PATH = {os.path.join(settings.BASE_DIR, 'media', 'sync_from_sheets.log')}")
        print("=== SYNC_FROM_SHEETS CALLED ===", file=sys.stderr, flush=True)
        logger.info("=== SYNC_FROM_SHEETS STARTED ===")
        logger.info(f"Mapping ID: {self.mapping.id}, Name: {self.mapping.name}")
        logger.info(f"Sheet: {self.mapping.sheet_name}, Spreadsheet ID: {self.mapping.spreadsheet_id}")
        logger.info(f"Header row: {self.mapping.header_row}, Start row: {self.mapping.start_row}")
        logger.info(f"Column mappings: {self.mapping.column_mappings}")
        logger.info("=== TEST LOG ENTRY === (should appear in sync_from_sheets.log)")
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

            # تحديث آخر صف تمت معالجته
            self.mapping.last_row_processed = self.stats['processed_rows'] + self.mapping.start_row - 1
            self.mapping.last_sync = timezone.now()
            self.mapping.save(update_fields=['last_row_processed', 'last_sync'])

            # إكمال المهمة
            task.complete_task(self.stats)

            return {
                'success': True,
                'stats': self.stats,
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
            logger.info(f"Fetching sheet data for sheet: {self.mapping.sheet_name}")
            logger.info(f"Spreadsheet ID: {self.mapping.spreadsheet_id}")
            logger.info(f"Header row: {self.mapping.header_row}, Start row: {self.mapping.start_row}")
            
            sheet_data = self.importer.get_sheet_data(self.mapping.sheet_name)
            
            if not sheet_data:
                logger.warning("No data returned from get_sheet_data()")
                return []
                
            logger.info(f"Retrieved {len(sheet_data)} rows of data from sheet")
            
            # Log first few rows for debugging
            for i, row in enumerate(sheet_data[:5]):
                logger.info(f"Row {i+1}: {row}")
                
            return sheet_data
            
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
            logger.debug(f"[DEBUG] البيانات المعالجة للصف {row_index}: {mapped_data}")

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

        for col_index, value in enumerate(row_data):
            field_type = self.mapping.get_column_mapping(col_index)
            if field_type and field_type != 'ignore':
                mapped_data[field_type] = value.strip() if value else ''

        return mapped_data

    def _process_customer(self, mapped_data: Dict[str, str], row_index: int,
                         task: GoogleSyncTask) -> Optional[Customer]:
        """
        معالجة بيانات العميل - يتم تخطي الصفوف التي لا تحتوي على اسم العميل فقط
        
        المعلمات:
            mapped_data: بيانات العميل المعالجة
            row_index: رقم الصف في الجدول
            task: مهمة المزامنة الحالية
        
        العائد:
            كائن العميل إذا تمت معالجته بنجاح، أو None إذا تم تخطيه
        """
        try:
            customer_name = mapped_data.get('customer_name', '').strip()
            if not customer_name:
                logger.info(f"[DEBUG] تخطي الصف {row_index}: لا يوجد اسم عميل")
                return None

            customer_phone = mapped_data.get('customer_phone', '').strip()
            customer_email = mapped_data.get('customer_email', '').strip()
            
            logger.debug(f"[DEBUG] معالجة العميل - الصف {row_index}: الاسم='{customer_name}', الهاتف='{customer_phone}', البريد='{customer_email}'")

            # البحث عن العميل الموجود بناءً على رقم الهاتف أو البريد الإلكتروني أو الاسم
            customer = None
            if customer_phone:
                customer = Customer.objects.filter(phone=customer_phone).first()
                if customer:
                    logger.debug(f"[DEBUG] تم العثور على العميل بالهاتف: {customer_phone}")
            
            if not customer and customer_email:
                customer = Customer.objects.filter(email=customer_email).first()
                if customer:
                    logger.debug(f"[DEBUG] تم العثور على العميل بالبريد الإلكتروني: {customer_email}")
            
            if not customer and customer_name:
                customer = Customer.objects.filter(name=customer_name).first()
                if customer:
                    logger.debug(f"[DEBUG] تم العثور على العميل بالاسم: {customer_name}")

            # إنشاء أو تحديث العميل
            if customer:
                if self.mapping.update_existing_customers:
                    logger.debug(f"[DEBUG] تحديث بيانات العميل الموجود: {customer_name} (ID: {customer.id})")
                    self._update_customer(customer, mapped_data)
                    self.stats['updated_customers'] += 1
                    logger.debug(f"[DEBUG] تم تحديث العميل: {customer_name} (ID: {customer.id})")
                else:
                    logger.debug(f"[DEBUG] تم العثور على العميل ولكن تحديث العملاء الحاليين معطل: {customer_name}")
            else:
                if self.mapping.auto_create_customers:
                    logger.debug(f"[DEBUG] إنشاء عميل جديد: {customer_name}")
                    customer = self._create_customer(mapped_data)
                    self.stats['created_customers'] += 1
                    logger.debug(f"[DEBUG] تم إنشاء عميل جديد: {customer_name} (ID: {customer.id})")
                else:
                    logger.debug(f"[DEBUG] لم يتم إنشاء عميل جديد - الإنشاء التلقائي معطل")

            return customer

        except Exception as e:
            error_msg = f"خطأ في معالجة العميل في الصف {row_index}: {str(e)}"
            logger.error(error_msg)
            logger.exception(e)
            raise

    def _create_customer(self, mapped_data: Dict[str, str]) -> Customer:
        """إنشاء عميل جديد مع احترام الكود والإعدادات الافتراضية"""
        customer_data = {
            'name': mapped_data.get('customer_name', ''),
            'phone': mapped_data.get('customer_phone', ''),
            'phone2': mapped_data.get('customer_phone2', ''),
            'email': mapped_data.get('customer_email', ''),
            'address': mapped_data.get('customer_address', ''),
        }

        # تعيين الكود من الجدول إذا كان موجوداً، وإلا لا يتم توليد كود عشوائي
        if mapped_data.get('code'):
            customer_data['code'] = mapped_data['code']
        # إذا لم يوجد كود في الجدول، لا يتم تعيينه (يترك للنظام أو قاعدة البيانات)

        # تحديد الفرع من الجدول أو من الإعدادات الافتراضية
        branch_name = mapped_data.get('branch', '')
        branch = None
        if branch_name:
            branch = Branch.objects.filter(name__icontains=branch_name).first()
        if not branch and self.mapping.default_branch:
            branch = self.mapping.default_branch
        if branch:
            customer_data['branch'] = branch

        # تعيين تصنيف العميل الافتراضي إذا لم يوجد
        if not mapped_data.get('customer_category') and self.mapping.default_customer_category:
            customer_data['category'] = self.mapping.default_customer_category

        # تعيين نوع العميل الافتراضي إذا لم يوجد
        if not mapped_data.get('customer_type') and self.mapping.default_customer_type:
            customer_data['customer_type'] = self.mapping.default_customer_type

        # تعيين تاريخ الإنشاء حسب الإعدادات
        if self.mapping.use_current_date_as_created:
            from django.utils import timezone
            customer_data['created_at'] = timezone.now()

        return Customer.objects.create(**customer_data)

    def _update_customer(self, customer: Customer, mapped_data: Dict[str, str]):
        """تحديث بيانات العميل مع تجاهل القيم الفارغة والمسافات البيضاء"""
        updated = False

        def clean_value(value):
            """تنظيف القيمة وإرجاعها إذا كانت تحتوي على محتوى حقيقي"""
            if value is None:
                return None
            value = str(value).strip()
            return value if value else None

        # تحديث الحقول إذا كانت تحتوي على قيم حقيقية (ليست فارغة أو مسافات بيضاء فقط)
        phone2 = clean_value(mapped_data.get('customer_phone2'))
        if phone2 is not None and not customer.phone2:
            customer.phone2 = phone2
            updated = True

        email = clean_value(mapped_data.get('customer_email'))
        if email is not None and not customer.email:
            customer.email = email
            updated = True

        address = clean_value(mapped_data.get('customer_address'))
        if address is not None and customer.address != address:
            customer.address = address
            updated = True

        if updated:
            customer.save()
            logger.debug(f"تم تحديث بيانات العميل: {customer.id} - {customer.name}")
        else:
            logger.debug(f"لم يتم تحديث بيانات العميل {customer.id} - لم يتم العثور على تغييرات")

        return updated

    def _process_order(self, mapped_data: Dict[str, str], customer: Customer,
                      row_index: int, task: GoogleSyncTask) -> Optional[Order]:
        """معالجة بيانات الطلب"""
        try:
            if not customer:
                return None

            order_number = mapped_data.get('order_number', '').strip()
            invoice_number = mapped_data.get('invoice_number', '').strip()

            # البحث عن الطلب الموجود
            order = None
            if order_number:
                order = Order.objects.filter(order_number=order_number).first()
            elif invoice_number:
                order = Order.objects.filter(invoice_number=invoice_number).first()

            # إنشاء أو تحديث الطلب
            if order:
                if self.mapping.update_existing_orders:
                    self._update_order(order, mapped_data, customer)
                    self.stats['updated_orders'] += 1
            else:
                if self.mapping.auto_create_orders:
                    order = self._create_order(mapped_data, customer)
                    self.stats['created_orders'] += 1

            return order

        except Exception as e:
            logger.error(f"خطأ في معالجة الطلب في الصف {row_index}: {str(e)}")
            raise

    def _create_order(self, mapped_data: Dict[str, str], customer: Customer) -> Order:
        """إنشاء طلب جديد"""
        order_data = {
            'customer': customer,
            'order_number': mapped_data.get('order_number') or self._generate_order_number(),
            'invoice_number': mapped_data.get('invoice_number', ''),
            'contract_number': mapped_data.get('contract_number', ''),
            'notes': mapped_data.get('notes', ''),
            'delivery_address': mapped_data.get('delivery_address', ''),
        }

        # تحديد نوع الطلب (استخدام الخيارات المتاحة في النموذج)
        order_type_name = mapped_data.get('order_type', '')
        if order_type_name:
            # البحث في الخيارات المتاحة
            type_mapping = {
                'قماش': 'fabric',
                'إكسسوار': 'accessory',
                'تركيب': 'installation',
                'معاينة': 'inspection',
                'نقل': 'transport',
                'تفصيل': 'tailoring',
            }
            order_type = type_mapping.get(order_type_name)
            if order_type:
                # سيتم حفظ نوع الطلب في ExtendedOrder لاحقاً
                pass

        # تحديد حالة التتبع
        tracking_status = mapped_data.get('tracking_status', '')
        if tracking_status:
            # تحويل حالة التتبع إلى القيم المقبولة
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

        # تحديد المبالغ
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

        # تحديد نوع التسليم
        delivery_type = mapped_data.get('delivery_type', '')
        if delivery_type:
            delivery_mapping = {
                'توصيل للمنزل': 'home',
                'استلام من الفرع': 'branch',
            }
            order_data['delivery_type'] = delivery_mapping.get(delivery_type, 'branch')

        # تحديد البائع
        salesperson_name = mapped_data.get('salesperson', '')
        if salesperson_name:
            salesperson = Salesperson.objects.filter(name__icontains=salesperson_name).first()
            if salesperson:
                order_data['salesperson'] = salesperson

        # تحديد الفرع
        if customer.branch:
            order_data['branch'] = customer.branch

        return Order.objects.create(**order_data)

    def _update_order(self, order: Order, mapped_data: Dict[str, str], customer: Customer):
        """تحديث بيانات الطلب"""
        updated = False

        # تحديث حالة التتبع
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

        # تحديث المبالغ
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

        # تحديث الملاحظات
        notes = mapped_data.get('notes', '')
        if notes and notes != order.notes:
            order.notes = notes
            updated = True

        if updated:
            order.save()

    def _process_inspection(self, mapped_data: Dict[str, str], customer: Customer,
                          order: Order, row_index: int, task: GoogleSyncTask):
        """معالجة بيانات المعاينة"""
        try:
            # التحقق من وجود معاينة للطلب
            existing_inspection = Inspection.objects.filter(order=order).first()
            if existing_inspection:
                return existing_inspection

            # إنشاء معاينة جديدة
            inspection_data = {
                'customer': customer,
                'order': order,
                'branch': customer.branch or order.branch,
                'request_date': timezone.now().date(),
                'scheduled_date': timezone.now().date() + timedelta(days=1),
                'notes': mapped_data.get('notes', ''),
            }

            # تحديد تاريخ المعاينة إذا كان متوفراً
            inspection_date = mapped_data.get('inspection_date', '')
            if inspection_date:
                try:
                    # محاولة تحويل التاريخ
                    parsed_date = datetime.strptime(inspection_date, '%Y-%m-%d').date()
                    inspection_data['scheduled_date'] = parsed_date
                except ValueError:
                    pass

            # تحديد نتيجة المعاينة
            inspection_result = mapped_data.get('inspection_result', '')
            if inspection_result:
                result_mapping = {
                    'مقبول': 'approved',
                    'مرفوض': 'rejected',
                    'يحتاج مراجعة': 'pending',
                }
                inspection_data['result'] = result_mapping.get(inspection_result, 'pending')

            # تحديد عدد الشبابيك
            windows_count = mapped_data.get('windows_count', '')
            if windows_count:
                try:
                    inspection_data['windows_count'] = int(windows_count)
                except (ValueError, TypeError):
                    pass

            inspection = Inspection.objects.create(**inspection_data)
            self.stats['created_inspections'] += 1

            return inspection

        except Exception as e:
            logger.error(f"خطأ في معالجة المعاينة في الصف {row_index}: {str(e)}")
            raise

    def _process_installation(self, mapped_data: Dict[str, str], customer: Customer,
                            order: Order, row_index: int, task: GoogleSyncTask):
        """معالجة بيانات التركيب"""
        try:
            # التحقق من وجود تركيب للطلب
            existing_installation = Installation.objects.filter(order=order).first()
            if existing_installation:
                return existing_installation

            # إنشاء تركيب جديد
            installation_data = {
                'order': order,
                'scheduled_date': timezone.now().date() + timedelta(days=7),
                'notes': mapped_data.get('notes', ''),
            }

            # تحديد حالة التركيب
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

            # تحديد فريق التركيب
            if customer.branch:
                team = InstallationTeam.objects.filter(branch=customer.branch, is_active=True).first()
                if team:
                    installation_data['team'] = team

            installation = Installation.objects.create(**installation_data)
            self.stats['created_installations'] += 1

            return installation

        except Exception as e:
            logger.error(f"خطأ في معالجة التركيب في الصف {row_index}: {str(e)}")
            raise

    def _generate_customer_code(self) -> str:
        """إنشاء كود عميل تلقائي"""
        last_customer = Customer.objects.filter(code__isnull=False).order_by('-id').first()
        if last_customer and last_customer.code:
            try:
                last_number = int(last_customer.code.replace('C', ''))
                return f"C{last_number + 1:04d}"
            except (ValueError, AttributeError):
                pass

        return f"C{Customer.objects.count() + 1:04d}"

    def _generate_order_number(self) -> str:
        """إنشاء رقم طلب تلقائي"""
        today = timezone.now().date()
        today_orders = Order.objects.filter(order_date__date=today).count()
        return f"ORD-{today.strftime('%Y%m%d')}-{today_orders + 1:03d}"

    def _create_conflict(self, task: GoogleSyncTask, conflict_type: str,
                        record_type: str, sheet_row: int, system_data: Dict,
                        sheet_data: Dict, description: str):
        """إنشاء تعارض في المزامنة"""
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
        """جلب البيانات من النظام للمزامنة العكسية"""
        # هذه الدالة ستحتاج تطوير أكثر حسب متطلبات المزامنة العكسية
        return []

    def _update_sheets_data(self, system_data: List[Dict[str, Any]], task: GoogleSyncTask):
        """
        تحديث بيانات Google Sheets بالبيانات من النظام
        
        المعلمات:
            system_data: قائمة بالبيانات من النظام للمزامنة
            task: مهمة المزامنة الحالية
        """
        if not system_data:
            logger.info("لا توجد بيانات للمزامنة مع Google Sheets")
            return

        try:
            # الحصول على بيانات الورقة الحالية
            sheet_data = self._get_sheet_data()
            if not sheet_data or len(sheet_data) < 2:  # يجب أن تحتوي على العناوين على الأقل
                logger.error("لا يمكن تحديث الورقة - لم يتم العثور على بيانات أو عناوين")
                return

            # الحصول على العناوين
            headers = sheet_data[0]
            
            # إنشاء قاموس لتعيين معرفات الصفوف
            row_map = {}
            for idx, row in enumerate(sheet_data[1:], start=2):  # الصفوف تبدأ من 2 (1 للعناوين)
                if len(row) > 0:  # التأكد من وجود معرف
                    row_map[str(row[0])] = idx  # حفظ رقم الصف

            # تجهيز البيانات للتحديث
            updates = []
            
            for record in system_data:
                if not record:
                    continue
                    
                record_id = str(record.get('id', ''))
                if not record_id:
                    continue

                # إعداد بيانات الصف المحدثة
                updated_row = []
                for header in headers:
                    # استخدام القيمة المحدثة إذا كانت موجودة، وإلا استخدم القيمة الفارغة
                    updated_row.append(str(record.get(header, '')))

                
                # إضافة الصف المحدث إلى قائمة التحديثات
                if record_id in row_map:
                    # تحديث صف موجود
                    updates.append({
                        'range': f"{self.mapping.sheet_name}!A{row_map[record_id]}:{chr(64 + len(headers))}{row_map[record_id]}",
                        'values': [updated_row]
                    })
                else:
                    # إضافة صف جديد
                    updates.append({
                        'range': f"{self.mapping.sheet_name}!A{len(sheet_data) + 1}:{chr(64 + len(headers))}{len(sheet_data) + 1}",
                        'values': [updated_row]
                    })
                    # تحديث row_map للصفوف المضافة
                    row_map[record_id] = len(sheet_data) + 1
                    sheet_data.append(updated_row)

            if not updates:
                logger.info("لا توجد تحديثات مطلوبة")
                return

            # تنفيذ التحديثات
            body = {
                'value_input_option': 'USER_ENTERED',
                'data': updates
            }
            
            # استخدام خدمة Google Sheets API
            service = self.importer.service
            if not service:
                logger.error("فشل الاتصال بخدمة Google Sheets")
                return
                
            response = service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.mapping.spreadsheet_id,
                body=body
            ).execute()
            
            logger.info(f"تم تحديث {len(updates)} صفوف في Google Sheets بنجاح")
            
            # تحديث إحصائيات المهمة
            task.rows_updated = len(updates)
            task.save(update_fields=['rows_updated', 'updated_at'])
            
        except Exception as e:
            error_msg = f"خطأ في تحديث Google Sheets: {str(e)}"
            logger.error(error_msg)
            logger.exception(e)
            raise Exception(error_msg) from e

    def _update_sheets_data(self, system_data: List[Dict[str, Any]], task: GoogleSyncTask):
        """
        تحديث بيانات Google Sheets بالبيانات من النظام
        
        المعلمات:
            system_data: قائمة بالبيانات من النظام للمزامنة
            task: مهمة المزامنة الحالية
        """
        if not system_data:
            logger.info("لا توجد بيانات للمزامنة مع Google Sheets")
            return

        try:
            # الحصول على بيانات الورقة الحالية
            sheet_data = self._get_sheet_data()
            if not sheet_data or len(sheet_data) < 2:  # يجب أن تحتوي على العناوين على الأقل
                logger.error("لا يمكن تحديث الورقة - لم يتم العثور على بيانات أو عناوين")
                return

            # الحصول على العناوين
            headers = sheet_data[0]
            
            # إنشاء قاموس لتعيين معرفات الصفوف
            row_map = {}
            for idx, row in enumerate(sheet_data[1:], start=2):  # الصفوف تبدأ من 2 (1 للعناوين)
                if len(row) > 0:  # التأكد من وجود معرف
                    row_map[str(row[0])] = idx  # حفظ رقم الصف

            # تجهيز البيانات للتحديث
            updates = []
            
            for record in system_data:
                if not record:
                    continue
                    
                record_id = str(record.get('id', ''))
                if not record_id:
                    continue

                # إعداد بيانات الصف المحدثة
                updated_row = []
                for header in headers:
                    # استخدام القيمة المحدثة إذا كانت موجودة، وإلا استخدم القيمة الفارغة
                    updated_row.append(str(record.get(header, '')))

                
                # إضافة الصف المحدث إلى قائمة التحديثات
                if record_id in row_map:
                    # تحديث صف موجود
                    updates.append({
                        'range': f"{self.mapping.sheet_name}!A{row_map[record_id]}:{chr(64 + len(headers))}{row_map[record_id]}",
                        'values': [updated_row]
                    })
                else:
                    # إضافة صف جديد
                    updates.append({
                        'range': f"{self.mapping.sheet_name}!A{len(sheet_data) + 1}:{chr(64 + len(headers))}{len(sheet_data) + 1}",
                        'values': [updated_row]
                    })
                    # تحديث row_map للصفوف المضافة
                    row_map[record_id] = len(sheet_data) + 1
                    sheet_data.append(updated_row)

            if not updates:
                logger.info("لا توجد تحديثات مطلوبة")
                return

            # تنفيذ التحديثات
            body = {
                'value_input_option': 'USER_ENTERED',
                'data': updates
            }
            
            # استخدام خدمة Google Sheets API
            service = self.importer.service
            if not service:
                logger.error("فشل الاتصال بخدمة Google Sheets")
                return
                
            response = service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.mapping.spreadsheet_id,
                body=body
            ).execute()
            
            logger.info(f"تم تحديث {len(updates)} صفوف في Google Sheets بنجاح")
            
            # تحديث إحصائيات المهمة
            task.rows_updated = len(updates)
            task.save(update_fields=['rows_updated', 'updated_at'])
            
        except Exception as e:
            error_msg = f"خطأ في تحديث Google Sheets: {str(e)}"
            logger.error(error_msg)
            logger.exception(e)
            raise Exception(error_msg) from e


class SyncScheduler:
    """مجدول المزامنة التلقائية"""

    @staticmethod
    def run_scheduled_syncs():
        """تشغيل المزامنة المجدولة"""
        try:
            # البحث عن المزامنات المستحقة
            due_schedules = GoogleSyncSchedule.objects.filter(
                is_active=True,
                next_run__lte=timezone.now()
            )

            for schedule in due_schedules:
                try:
                    # تشغيل المزامنة
                    sync_service = AdvancedSyncService(schedule.mapping)
                    result = sync_service.sync_from_sheets()

                    # تسجيل النتيجة
                    schedule.record_run(success=result.get('success', False))

                    logger.info(f"تم تشغيل المزامنة المجدولة: {schedule.mapping.name}")

                except Exception as e:
                    logger.error(f"خطأ في تشغيل المزامنة المجدولة {schedule.mapping.name}: {str(e)}")
                    schedule.record_run(success=False)

        except Exception as e:
            logger.error(f"خطأ في مجدول المزامنة: {str(e)}")
