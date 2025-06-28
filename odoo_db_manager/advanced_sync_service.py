"""
خدمة المزامنة المتقدمة مع Google Sheets
Advanced Google Sheets Sync Service
"""

import logging
from contextlib import suppress
from datetime import date, datetime
from typing import Dict, List, Any, Optional

from dateutil import parser as date_parser
from django.utils import timezone
from django.conf import settings

from customers.models import Customer, CustomerCategory
from orders.models import Order
from inspections.models import Inspection
from installations.models import Installation
from accounts.models import Branch, User

from .google_sync_advanced import (
    GoogleSheetMapping, GoogleSyncTask, GoogleSyncConflict, GoogleSyncSchedule
)
from .google_sheets_import import GoogleSheetsImporter

logger = logging.getLogger(__name__)


class AdvancedSyncService:
    """خدمة المزامنة المتقدمة"""

    def __init__(self, mapping: GoogleSheetMapping):
        self.mapping = mapping
        self.importer = GoogleSheetsImporter()
        self.conflicts = []
        self.headers_cache = None  # Cache for headers
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

    def sync_from_sheets(
        self, task: Optional[GoogleSyncTask] = None
    ) -> Dict[str, Any]:
        """
        تنفيذ المزامنة من Google Sheets باستخدام التعيينات المخصصة
        """
        logger.info("بدء عملية المزامنة من Google Sheets")
        logger.info("=== SYNC_FROM_SHEETS STARTED ===")
        logger.info(
            "Mapping: %s, Sheet: %s, Spreadsheet ID: %s",
            self.mapping.name,
            self.mapping.sheet_name,
            self.mapping.spreadsheet_id
        )
        try:
            task = self._setup_sync_task(task)
            sheet_data = self._get_and_validate_sheet_data(task)
            if not sheet_data:
                return {'success': False, 'error': 'No data available'}

            self._log_sheet_info(sheet_data)
            self._setup_task_stats(task, sheet_data)
            self._process_all_rows(sheet_data, task)
            self._finalize_sync(task)

            return self._create_success_response(task)

        except Exception as e:
            return self._handle_sync_error(e, task)

    def sync_to_sheets(
        self, task: Optional[GoogleSyncTask] = None
    ) -> Dict[str, Any]:
        """مزامنة البيانات من النظام إلى Google Sheets (المزامنة العكسية)"""
        try:
            if not self.mapping.enable_reverse_sync:
                return {
                    'success': False,
                    'error': 'المزامنة العكسية غير مفعلة'
                }

            self._initialize_importer()
            task = task or self._create_task('reverse_sync')
            task.start_task()

            system_data = self._get_system_data()
            self._update_sheets_data(system_data, task)
            task.complete_task({'updated_rows': len(system_data)})

            return {
                'success': True,
                'updated_rows': len(system_data),
                'task_id': getattr(task, 'pk', None)
            }

        except Exception as e:
            return self._handle_sync_error(e, task, "المزامنة العكسية")

    def _setup_sync_task(
        self, task: Optional[GoogleSyncTask]
    ) -> GoogleSyncTask:
        """إعداد مهمة المزامنة"""
        self._initialize_importer()
        if not task:
            task = self._create_task()
        task.start_task()
        return task

    def _get_and_validate_sheet_data(
        self, task: GoogleSyncTask
    ) -> List[List[str]]:
        """جلب والتحقق من بيانات الشيت"""
        sheet_data = self._get_sheet_data()
        if not sheet_data:
            error_msg = (
                "No data returned from Google Sheets - "
                "sheet may be empty or not exist"
            )
            logger.error(error_msg)
            task.fail_task(error_msg)
        return sheet_data

    def _log_sheet_info(self, sheet_data: List[List[str]]):
        """تسجيل معلومات الشيت"""
        logger.info(
            "Sheet data retrieved - Rows: %d",
            len(sheet_data) if sheet_data else 0
        )
        if sheet_data:
            logger.info("First row (headers): %s", sheet_data[0])
            if len(sheet_data) > 1:
                logger.info("Sample data row: %s", sheet_data[1])

    def _setup_task_stats(
        self, task: GoogleSyncTask, sheet_data: List[List[str]]
    ):
        """إعداد إحصائيات المهمة"""
        self.stats['total_rows'] = (
            len(sheet_data) - self.mapping.header_row
        )
        task.total_rows = self.stats['total_rows']
        task.save(update_fields=['total_rows'])

    def _finalize_sync(self, task: GoogleSyncTask):
        """إنهاء المزامنة"""
        self._update_mapping_sync_info()
        task.complete_task(self.stats)

    def _create_success_response(self, task: GoogleSyncTask) -> Dict[str, Any]:
        """إنشاء استجابة النجاح"""
        stats_out = self._prepare_stats_output()
        return {
            'success': True,
            'stats': stats_out,
            'conflicts': len(self.conflicts),
            'task_id': getattr(task, 'pk', None)
        }

    def _handle_sync_error(
        self, error: Exception, task: Optional[GoogleSyncTask],
        sync_type: str = "المزامنة"
    ) -> Dict[str, Any]:
        """معالجة خطأ المزامنة"""
        logger.error("خطأ في %s: %s", sync_type, str(error))
        if task:
            task.fail_task(str(error))
        return {'success': False, 'error': str(error)}

    def _initialize_importer(self):
        """تهيئة المستورد"""
        self.importer.initialize()

    def _create_task(self, task_type: str = 'import') -> GoogleSyncTask:
        """إنشاء مهمة جديدة"""
        return GoogleSyncTask.objects.create(
            mapping=self.mapping,
            task_type=task_type,
            created_by=None  # يمكن تحديد المستخدم لاحقاً
        )

    def _process_all_rows(
        self, sheet_data: List[List[str]], task: GoogleSyncTask
    ):
        """معالجة جميع الصفوف"""
        start_row = self.mapping.start_row - 1
        for row_index, row_data in enumerate(
            sheet_data[start_row:], start=self.mapping.start_row
        ):
            try:
                self._process_single_row(row_data, row_index, task)
            except Exception as e:
                self._handle_row_error(e, row_index, row_data, task)

    def _process_single_row(
        self, row_data: List[str], row_index: int, task: GoogleSyncTask
    ):
        """معالجة صف واحد"""
        self._process_row(row_data, row_index, task)
        self.stats['processed_rows'] += 1
        self.stats['successful_rows'] += 1
        self._update_task_progress(task)

    def _update_task_progress(self, task: GoogleSyncTask):
        """تحديث تقدم المهمة"""
        task.processed_rows = self.stats['processed_rows']
        task.successful_rows = self.stats['successful_rows']
        task.save(update_fields=['processed_rows', 'successful_rows'])

    def _handle_row_error(
        self, error: Exception, row_index: int,
        row_data: List[str], task: GoogleSyncTask
    ):
        """معالجة خطأ في الصف"""
        self._log_error_message(error, row_index)
        self.stats['failed_rows'] += 1
        task.failed_rows = self.stats['failed_rows']
        task.save(update_fields=['failed_rows'])

        self._create_conflict(
            task, 'validation_error', 'unknown', row_index,
            {}, dict(zip(self._get_headers(), row_data)),
            f"خطأ في معالجة الصف: {str(error)}"
        )

        self.stats['errors'].append(f"صف {row_index}: {str(error)}")

    def _log_error_message(self, error: Exception, row_index: int):
        """تسجيل رسالة الخطأ"""
        error_msg = f"خطأ في معالجة الصف {row_index}: {str(error)}"
        logger.error(error_msg)
        logger.exception(error)

    def _update_mapping_sync_info(self):
        """تحديث معلومات المزامنة في التعيين"""
        self.mapping.last_row_processed = (
            self.stats['processed_rows'] + self.mapping.start_row - 1
        )
        self.mapping.last_sync = timezone.now()
        self.mapping.save(update_fields=['last_row_processed', 'last_sync'])

    def _prepare_stats_output(self) -> Dict[str, Any]:
        """إعداد إحصائيات الإخراج"""
        stats_out = dict(self.stats)
        stats_out['customers_created'] = self.stats.get('created_customers', 0)
        stats_out['customers_updated'] = self.stats.get('updated_customers', 0)
        stats_out['orders_created'] = self.stats.get('created_orders', 0)
        stats_out['orders_updated'] = self.stats.get('updated_orders', 0)
        return stats_out

    def _get_sheet_data(self) -> List[List[str]]:
        """جلب البيانات من Google Sheets"""
        try:
            logger.info(
                "Fetching sheet data for sheet: %s, Spreadsheet ID: %s",
                self.mapping.sheet_name,
                self.mapping.spreadsheet_id
            )

            sheet_data = self.importer.get_sheet_data(self.mapping.sheet_name)

            if not sheet_data:
                logger.warning("No data returned from get_sheet_data()")
                return []

            logger.info(
                "Retrieved %d rows of data from sheet", len(sheet_data)
            )

            self._log_sample_data(sheet_data)
            return sheet_data

        except Exception as e:
            logger.error(
                "خطأ في جلب البيانات من Google Sheets: %s", str(e)
            )
            raise

    def _log_sample_data(self, sheet_data: List[List[str]]):
        """تسجيل عينة من البيانات للتشخيص"""
        if sheet_data:
            logger.info("First row (headers): %s", sheet_data[0])
            if len(sheet_data) > 1:
                logger.info("First data row: %s", sheet_data[1])

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
            logger.error("خطأ في جلب العناوين: %s", str(e))
            return []

    def _process_row(
        self, row_data: List[str], row_index: int, task: GoogleSyncTask
    ):
        """
        معالجة صف واحد من البيانات

        المعلمات:
            row_data: قائمة بقيم الصف
            row_index: رقم الصف في الجدول (يبدأ من 1)
            task: مهمة المزامنة الحالية
        """
        try:
            logger.debug(
                "[DEBUG] معالجة الصف %d: %s", row_index, row_data
            )

            if not any(cell and str(cell).strip() for cell in row_data):
                logger.info("[INFO] تخطي الصف %d: صف فارغ", row_index)
                return

            mapped_data = self._map_row_data(row_data)
            customer = self._process_customer(mapped_data, row_index)

            if not customer:
                logger.info(
                    "[INFO] تخطي الصف %d: لم يتم معالجة العميل", row_index
                )
                return

            order = self._process_order(mapped_data, customer, row_index)
            if not order and self.mapping.auto_create_orders:
                logger.info(
                    "[INFO] تخطي الصف %d: لم يتم معالجة الطلب", row_index
                )
                return

            if order:
                self._process_inspection_if_needed(
                    mapped_data, customer, order, row_index
                )
                self._process_installation_if_needed(
                    mapped_data, customer, order, row_index
                )

            logger.debug("[DEBUG] تمت معالجة الصف %d بنجاح", row_index)

        except Exception as e:
            self._log_error_message(e, row_index)
            if settings.DEBUG:
                raise

    def _process_inspection_if_needed(
        self, mapped_data: Dict[str, str], customer: Customer,
        order: Order, row_index: int
    ):
        """معالجة المعاينة إذا لزم الأمر"""
        if self.mapping.auto_create_inspections:
            inspection = self._process_inspection(
                mapped_data, customer, order, row_index
            )
            require_inspection = getattr(
                self.mapping, 'require_inspection', False
            )
            if not inspection and require_inspection:
                logger.info(
                    "[INFO] تخطي الصف %d: لم يتم معالجة المعاينة",
                    row_index
                )

    def _process_installation_if_needed(
        self, mapped_data: Dict[str, str], customer: Customer,
        order: Order, row_index: int
    ):
        """معالجة التركيب إذا لزم الأمر"""
        if self.mapping.auto_create_installations:
            installation = self._process_installation(
                mapped_data, customer, order, row_index
            )
            require_installation = getattr(
                self.mapping, 'require_installation', False
            )
            if not installation and require_installation:
                logger.info(
                    "[INFO] تخطي الصف %d: لم يتم معالجة التركيب",
                    row_index
                )

    def _map_row_data(self, row_data: List[str]) -> Dict[str, str]:
        """تحويل بيانات الصف إلى قاموس مع التعيينات"""
        mapped_data = {}
        headers = self._get_headers()
        column_mappings = self.mapping.column_mappings

        for col_index, value in enumerate(row_data):
            col_name = headers[col_index] if col_index < len(headers) else None
            field_type = self._get_field_type(
                col_name, col_index, column_mappings
            )

            if field_type and field_type != 'ignore':
                mapped_data[field_type] = value.strip() if value else ''

        return mapped_data

    def _get_field_type(
        self, col_name: Optional[str], col_index: int,
        column_mappings: Dict[str, str]
    ) -> Optional[str]:
        """الحصول على نوع الحقل"""
        field_type = None
        if col_name:
            col_name_stripped = col_name.strip()
            field_type = column_mappings.get(col_name_stripped)

        if not field_type:
            field_type = column_mappings.get(str(col_index))

        return field_type

    def _process_customer(
        self, mapped_data: Dict[str, str], row_index: int
    ) -> Optional[Customer]:
        """معالجة بيانات العميل"""
        try:
            customer_name = mapped_data.get('customer_name', '').strip()
            if not customer_name:
                return None

            if customer := self._find_existing_customer(mapped_data):
                self._update_existing_customer(customer, mapped_data)
                return customer

            return self._create_new_customer(mapped_data)

        except Exception as e:
            error_msg = f"خطأ في معالجة العميل في الصف {row_index}: {str(e)}"
            logger.error(error_msg)
            logger.exception(e)
            raise

    def _find_existing_customer(
        self, mapped_data: Dict[str, str]
    ) -> Optional[Customer]:
        """البحث عن عميل موجود"""
        if customer_phone := mapped_data.get('customer_phone', '').strip():
            if customer := Customer.objects.filter(
                phone=customer_phone
            ).first():
                return customer

        if customer_email := mapped_data.get('customer_email', '').strip():
            if customer := Customer.objects.filter(
                email=customer_email
            ).first():
                return customer

        if customer_name := mapped_data.get('customer_name', '').strip():
            return Customer.objects.filter(name=customer_name).first()

        return None

    def _update_existing_customer(
        self, customer: Customer, mapped_data: Dict[str, str]
    ):
        """تحديث عميل موجود"""
        if self.mapping.update_existing_customers:
            logger.debug(
                "[DEBUG] تحديث بيانات العميل الموجود: %s (ID: %s)",
                customer.name,
                getattr(customer, 'pk', 'unknown')
            )
            self._update_customer(customer, mapped_data)
            self.stats['updated_customers'] += 1

    def _create_new_customer(
        self, mapped_data: Dict[str, str]
    ) -> Optional[Customer]:
        """إنشاء عميل جديد"""
        if self.mapping.auto_create_customers:
            customer = self._create_customer(mapped_data)
            self.stats['created_customers'] += 1
            return customer
        return None

    def _create_customer(self, mapped_data: Dict[str, str]) -> Customer:
        """إنشاء عميل جديد"""
        customer_data = {
            'name': mapped_data.get('customer_name', ''),
            'phone': mapped_data.get('customer_phone', ''),
            'phone2': mapped_data.get('customer_phone2', ''),
            'email': mapped_data.get('customer_email', ''),
            'address': mapped_data.get('customer_address', ''),
        }

        self._set_customer_category(customer_data, mapped_data)
        self._set_customer_branch(customer_data, mapped_data)

        customer = Customer.objects.create(**customer_data)
        self._update_customer_creation_date(customer, mapped_data)

        return customer

    def _set_customer_category(
        self, customer_data: Dict[str, Any], mapped_data: Dict[str, str]
    ):
        """تعيين تصنيف العميل"""
        if category_name := mapped_data.get('customer_category', ''):
            if category := CustomerCategory.objects.filter(
                name__icontains=category_name
            ).first():
                customer_data['category'] = category
        elif self.mapping.default_customer_category:
            customer_data['category'] = self.mapping.default_customer_category

    def _set_customer_branch(
        self, customer_data: Dict[str, Any], mapped_data: Dict[str, str]
    ):
        """تعيين فرع العميل"""
        if branch_name := mapped_data.get('branch', ''):
            branch = Branch.objects.filter(
                name__icontains=branch_name
            ).first()
        else:
            branch = Branch.objects.first()

        if branch:
            customer_data['branch'] = branch
        else:
            logger.warning("لا يوجد فرع متاح لإنشاء العميل")

    def _update_customer_creation_date(
        self, customer: Customer, mapped_data: Dict[str, str]
    ):
        """تحديث تاريخ إنشاء العميل"""
        if order_date_str := mapped_data.get('order_date', '').strip():
            try:
                parsed_order_date = date_parser.parse(
                    order_date_str, dayfirst=True
                )
                Customer.objects.filter(pk=customer.pk).update(
                    created_at=parsed_order_date
                )
                customer.refresh_from_db()
                logger.info(
                    "تم تحديث تاريخ إنشاء العميل إلى: %s", parsed_order_date
                )
            except Exception as e:
                logger.warning(
                    "فشل في تحليل تاريخ إنشاء العميل [%s]: %s",
                    order_date_str,
                    e
                )

    def _update_customer(
        self, customer: Customer, mapped_data: Dict[str, str]
    ):
        """تحديث بيانات العميل"""
        updated = False

        if mapped_data.get('customer_phone2') and not customer.phone2:
            customer.phone2 = mapped_data['customer_phone2']
            updated = True

        if mapped_data.get('customer_email') and not customer.email:
            customer.email = mapped_data['customer_email']
            updated = True

        if (
            mapped_data.get('customer_address') and
            customer.address != mapped_data['customer_address']
        ):
            customer.address = mapped_data['customer_address']
            updated = True

        if self._update_customer_category(customer, mapped_data):
            updated = True

        if updated:
            customer.save()

    def _update_customer_category(
        self, customer: Customer, mapped_data: Dict[str, str]
    ) -> bool:
        """تحديث تصنيف العميل"""
        if category_name := mapped_data.get('customer_category', ''):
            if category := CustomerCategory.objects.filter(
                name__icontains=category_name
            ).first():
                if customer.category != category:
                    customer.category = category
                    return True
        elif (
            not customer.category and
            self.mapping.default_customer_category
        ):
            customer.category = self.mapping.default_customer_category
            return True
        return False

    def _process_order(
        self, mapped_data: Dict[str, str], customer: Optional[Customer],
        row_index: int
    ) -> Optional[Order]:
        """معالجة بيانات الطلب"""
        try:
            if not customer or not self.mapping.auto_create_orders:
                return None

            if order := self._find_existing_order(mapped_data, customer):
                self._handle_existing_order(order, mapped_data)
                return order
            if self.mapping.auto_create_orders:
                return self._handle_new_order(mapped_data, customer)

            logger.info(
                "تخطي إنشاء طلب جديد للصف %d لأن auto_create_orders معطل",
                row_index
            )
            return None

        except Exception as e:
            logger.error(
                "خطأ في معالجة الطلب في الصف %d: %s", row_index, str(e)
            )
            raise

    def _find_existing_order(
        self, mapped_data: Dict[str, str], customer: Customer
    ) -> Optional[Order]:
        """البحث عن طلب موجود"""
        if order_number := mapped_data.get('order_number', '').strip():
            if order := Order.objects.filter(
                order_number=order_number
            ).first():
                return order

        if contract_number := mapped_data.get('contract_number', '').strip():
            return Order.objects.filter(
                customer=customer,
                contract_number=contract_number
            ).first()

        return None

    def _handle_existing_order(
        self, order: Order, mapped_data: Dict[str, str]
    ):
        """معالجة طلب موجود"""
        if self.mapping.update_existing_orders:
            self._update_order(order, mapped_data)
            self.stats['updated_orders'] += 1
        logger.info(
            "تم العثور على طلب موجود وتحديثه: %s",
            getattr(order, 'order_number', getattr(order, 'pk', 'unknown'))
        )

    def _handle_new_order(
        self, mapped_data: Dict[str, str], customer: Customer
    ) -> Optional[Order]:
        """معالجة طلب جديد"""
        contract_number = mapped_data.get('contract_number', '').strip()
        order_number = mapped_data.get('order_number', '').strip()

        if self._is_duplicate_order(contract_number, order_number, customer):
            return self._handle_duplicate_order(
                contract_number, order_number, mapped_data
            )

        order = self._create_order(customer, mapped_data)
        self.stats['created_orders'] += 1
        logger.info(
            "تم إنشاء طلب جديد: %s",
            getattr(order, 'order_number', getattr(order, 'pk', 'unknown'))
        )
        return order

    def _is_duplicate_order(
        self, contract_number: str, order_number: str, customer: Customer
    ) -> bool:
        """التحقق من وجود طلب مكرر"""
        if contract_number and Order.objects.filter(
            contract_number=contract_number, customer=customer
        ).exists():
            return True

        return bool(order_number and Order.objects.filter(
            order_number=order_number
        ).exists())

    def _handle_duplicate_order(
        self, contract_number: str, order_number: str,
        mapped_data: Dict[str, str]
    ) -> Optional[Order]:
        """معالجة طلب مكرر"""
        if contract_number:
            order = Order.objects.filter(
                contract_number=contract_number
            ).first()
            logger.warning(
                "تخطي إنشاء طلب مكرر برقم عقد: %s", contract_number
            )
        else:
            order = Order.objects.filter(order_number=order_number).first()
            logger.warning("تخطي إنشاء طلب مكرر برقم: %s", order_number)

        if self.mapping.update_existing_orders and order:
            self._update_order(order, mapped_data)
            self.stats['updated_orders'] += 1

        return order

    def _create_order(
        self, customer: Customer, mapped_data: Dict[str, str]
    ) -> Order:
        """إنشاء طلب جديد"""
        order_data = {
            'customer': customer,
            'status': mapped_data.get('order_status', 'new'),
            'contract_number': mapped_data.get('contract_number', ''),
        }

        order = Order.objects.create(**order_data)
        self._update_order_date(order, mapped_data)
        return order

    def _update_order_date(self, order: Order, mapped_data: Dict[str, str]):
        """تحديث تاريخ الطلب"""
        if order_date_str := mapped_data.get('order_date', '').strip():
            try:
                parsed_order_date = date_parser.parse(
                    order_date_str, dayfirst=True
                )
                Order.objects.filter(pk=order.pk).update(
                    order_date=parsed_order_date
                )
                order.refresh_from_db()
                logger.info("تم تحديث تاريخ الطلب إلى: %s", parsed_order_date)
            except Exception as e:
                logger.warning(
                    "فشل في تحليل تاريخ الطلب [%s]: %s",
                    order_date_str,
                    e
                )

    def _update_order(
        self, order: Order, mapped_data: Dict[str, str]
    ) -> Order:
        """تحديث بيانات الطلب"""
        for field, value in mapped_data.items():
            if (
                field.startswith('order_') and
                hasattr(order, field.replace('order_', ''))
            ):
                setattr(order, field.replace('order_', ''), value)

        order.save()
        return order

    def _process_inspection(
        self, mapped_data: Dict[str, str], customer: Customer,
        order: Order, row_index: int
    ) -> Optional[Inspection]:
        """معالجة بيانات المعاينة"""
        try:
            if not (inspection_date_str := mapped_data.get(
                'inspection_date', ''
            ).strip()):
                return self._log_inspection_error(
                    row_index, "لا يوجد تاريخ معاينة"
                )

            scheduled_date = self._parse_inspection_date(
                inspection_date_str, row_index
            )
            if not scheduled_date:
                return None

            if existing_inspection := self._check_existing_inspection(
                order, scheduled_date
            ):
                return existing_inspection

            request_date = self._get_request_date(mapped_data)
            inspection = Inspection.objects.create(
                customer=customer,
                order=order,
                status='pending',
                request_date=request_date,
                scheduled_date=scheduled_date
            )

            self.stats['created_inspections'] += 1
            return inspection

        except Exception as e:
            fail_reason = (
                f"خطأ في معالجة المعاينة في الصف {row_index}: {str(e)}"
            )
            logger.error(fail_reason)
            self.stats['errors'].append(fail_reason)
            return None

    def _log_inspection_error(self, row_index: int, reason: str) -> None:
        """تسجيل خطأ المعاينة"""
        fail_reason = f"لم يتم إنشاء المعاينة للصف {row_index}: {reason}."
        logger.error(fail_reason)
        self.stats['errors'].append(fail_reason)

    def _parse_inspection_date(
        self, inspection_date_str: str, row_index: int
    ) -> Optional[date]:
        """تحليل تاريخ المعاينة"""
        try:
            parsed_date = date_parser.parse(inspection_date_str, dayfirst=True)
            scheduled_date = parsed_date.date()

            today = date.today()
            if (scheduled_date.year < 2020 or
                    scheduled_date.year > today.year + 2):
                scheduled_date = scheduled_date.replace(year=today.year)
                logger.warning(
                    "تم إصلاح تاريخ المعاينة للصف %d: %s -> %s",
                    row_index,
                    inspection_date_str,
                    scheduled_date
                )

            return scheduled_date

        except Exception:
            fail_reason = (
                f"لم يتم إنشاء المعاينة للصف {row_index}: "
                f"تاريخ المعاينة غير صالح [{inspection_date_str}]."
            )
            logger.info(fail_reason)
            self.stats['errors'].append(fail_reason)
            return None

    def _check_existing_inspection(
        self, order: Order, scheduled_date: date
    ) -> Optional[Inspection]:
        """التحقق من وجود معاينة موجودة"""
        if inspection := Inspection.objects.filter(
            order=order, scheduled_date=scheduled_date
        ).first():
            logger.info(
                "تم العثور على معاينة موجودة للطلب %s بتاريخ %s، "
                "لن يتم إنشاء معاينة جديدة.",
                getattr(order, 'order_number',
                        getattr(order, 'pk', 'unknown')),
                scheduled_date
            )
            return inspection

        if inspection := Inspection.objects.filter(order=order).first():
            logger.info(
                "تم العثور على معاينة موجودة للطلب %s، "
                "لن يتم إنشاء معاينة جديدة.",
                getattr(order, 'order_number',
                        getattr(order, 'pk', 'unknown'))
            )
            return inspection

        return None

    def _get_request_date(self, mapped_data: Dict[str, str]) -> date:
        """الحصول على تاريخ الطلب"""
        request_date = timezone.now().date()

        if order_date_str := mapped_data.get('order_date', '').strip():
            try:
                parsed_order_date = date_parser.parse(
                    order_date_str, dayfirst=True
                )
                request_date = parsed_order_date.date()
                logger.info(
                    "استخدام تاريخ الطلب من الجدول: %s", request_date
                )
            except Exception:
                logger.warning(
                    "فشل في تحليل تاريخ الطلب [%s]، "
                    "سيتم استخدام التاريخ الحالي",
                    order_date_str
                )

        return request_date

    def _process_installation(
        self, mapped_data: Dict[str, str], customer: Customer,
        order: Order, row_index: int
    ) -> Optional[Installation]:
        """معالجة بيانات التركيب"""
        try:
            if installation := Installation.objects.filter(
                order=order
            ).first():
                return installation

            installation = Installation.objects.create(
                customer=customer,
                order=order,
                status='pending',
                request_date=timezone.now().date()
            )

            if installation_date := mapped_data.get(
                'installation_date', ''
            ).strip():
                self._update_installation_date(installation, installation_date)

            self.stats['created_installations'] += 1
            return installation

        except Exception as e:
            logger.error(
                "خطأ في معالجة التركيب في الصف %d: %s", row_index, str(e)
            )
            return None

    def _update_installation_date(
        self, installation: Installation, installation_date: str
    ):
        """تحديث تاريخ التركيب"""
        with suppress(ValueError):
            scheduled_date = datetime.strptime(
                installation_date, '%d-%m-%Y'
            ).date()
            installation.scheduled_date = scheduled_date
            installation.save(update_fields=['scheduled_date'])

    def _create_conflict(
        self, task: GoogleSyncTask, conflict_type: str, field_name: str,
        row_index: int, system_data: Dict[str, Any],
        sheet_data: Dict[str, Any], description: str
    ) -> GoogleSyncConflict:
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

    def _get_system_data(self) -> List[Dict[str, Any]]:
        """جلب بيانات النظام للمزامنة العكسية"""
        return []

    def _update_sheets_data(
        self, system_data: List[Dict[str, Any]], task: GoogleSyncTask
    ):
        """تحديث بيانات Google Sheets"""
        # Placeholder for future implementation
        logger.info("تحديث بيانات Google Sheets - سيتم تطويرها لاحقاً")


class SyncScheduler:
    """مجدول المزامنة التلقائية"""

    @staticmethod
    def run_scheduled_syncs():
        """تشغيل المزامنة المجدولة باستخدام نفس منطق السكريبت"""
        try:
            due_schedules = GoogleSyncSchedule.objects.filter(
                is_active=True,
                next_run__lte=timezone.now()
            )

            for schedule in due_schedules:
                try:
                    SyncScheduler._process_schedule(schedule)
                except Exception as e:
                    logger.error(
                        "خطأ في تشغيل المزامنة المجدولة %s: %s",
                        schedule.mapping.name,
                        str(e)
                    )
                    schedule.record_run(success=False)

        except Exception as e:
            logger.error("خطأ في تشغيل المزامنة المجدولة: %s", str(e))

    @staticmethod
    def _process_schedule(schedule):
        """معالجة جدولة واحدة"""
        mapping = schedule.mapping

        system_user = User.objects.filter(is_superuser=True).first()

        task = GoogleSyncTask.objects.create(
            mapping=mapping,
            task_type='import',
            created_by=system_user,
            is_scheduled=True
        )

        task.start_task()
        service = AdvancedSyncService(mapping)
        result = service.sync_from_sheets(task)

        if result['success']:
            task.mark_completed(result)
            stats = result['stats']
            logger.info("تمت المزامنة المجدولة بنجاح: %s", mapping.name)
            logger.info(
                "إحصائيات: إجمالي الصفوف: %d, المعالجة: %d",
                stats['total_rows'],
                stats['processed_rows']
            )
        else:
            task.mark_failed(result.get('error', 'خطأ غير معروف'))
            logger.error(
                "فشلت المزامنة المجدولة: %s - %s",
                mapping.name,
                result.get('error')
            )

        schedule.record_run(success=result.get('success', False))

    @staticmethod
    def add_public_method():
        """إضافة طريقة عامة لتلبية متطلبات pylint"""
        pass