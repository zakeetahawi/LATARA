"""
خدمة محسنة لاستيراد البيانات من Google Sheets - استيراد ديناميكي كامل مع دعم حذف البيانات والعلاقات (مثل التصنيف) وتعيين حقول التواريخ من Google Sheets
"""
import logging
import json
from django.db import transaction
from django.apps import apps
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

class GoogleSheetsImporter:
    def __init__(self):
        self.service = None
        self.config = None

    def initialize(self):
        """تهيئة الخدمة مع Google Sheets API"""
        try:
            from .google_sync import GoogleSyncConfig
            self.config = GoogleSyncConfig.get_active_config()

            if not self.config:
                raise Exception(
                    "لا يوجد إعداد مزامنة نشط. يرجى إعداد Google Sheets أولاً."
                )

            credentials_data = self.config.get_credentials()
            if not credentials_data:
                raise Exception(
                    "لا يمكن قراءة بيانات الاعتماد. "
                    "تأكد من تحميل ملف اعتماد صحيح (يفضل إعادة رفع الملف من جديد)."
                )

            if isinstance(credentials_data, str):
                raise Exception(
                    f"ملف بيانات الاعتماد غير صالح (نص غير قابل للتحويل):\n{credentials_data}\n"
                    "يرجى حذف ملف الاعتماد ورفعه من جديد بصيغة JSON صافية."
                )
            if isinstance(credentials_data, str):
                try:
                    credentials_data = json.loads(credentials_data)
                except Exception:
                    pass
            if isinstance(credentials_data, str):
                try:
                    credentials_data = json.loads(credentials_data)
                except Exception:
                    raise Exception(
                        f"ملف بيانات الاعتماد غير صالح (نص غير قابل للتحويل): {credentials_data!r}"
                    )

            if not isinstance(credentials_data, dict):
                raise Exception(
                    f"ملف بيانات الاعتماد غير صالح. النوع: {type(credentials_data)}. القيمة: {credentials_data!r}"
                )

            required_fields = [
                'type', 'project_id', 'private_key_id',
                'private_key', 'client_email', 'client_id'
            ]
            missing_fields = [
                field for field in required_fields
                if field not in credentials_data
            ]
            if missing_fields:
                raise Exception(
                    "بيانات الاعتماد غير مكتملة. "
                    f"الحقول المفقودة: {', '.join(missing_fields)}"
                )
            if credentials_data.get('type') != 'service_account':
                raise Exception(
                    "نوع الحساب غير صحيح. يجب أن يكون 'service_account'"
                )

            creds = service_account.Credentials.from_service_account_info(
                credentials_data,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            self.service = build('sheets', 'v4', credentials=creds)
            self._test_connection()
        except Exception as e:
            logger.error(f"فشل في تهيئة خدمة Google Sheets: {str(e)}")
            raise

    def _test_connection(self):
        try:
            if not self.service or not self.config:
                raise Exception("لم يتم تهيئة الخدمة بشكل صحيح")
            spreadsheet = (
                self.service.spreadsheets()
                .get(spreadsheetId=self.config.spreadsheet_id)
                .execute()
            )
            title = spreadsheet.get('properties', {}).get('title', 'Unknown')
            logger.info(f"تم الاتصال بنجاح مع جدول البيانات: {title}")
        except Exception as e:
            error_msg = str(e).lower()
            if 'not found' in error_msg or '404' in error_msg:
                raise Exception(
                    "جدول البيانات غير موجود أو معرف الجدول غير صحيح."
                )
            elif 'permission' in error_msg or '403' in error_msg:
                creds = self.config.get_credentials()
                client_email = creds.get('client_email', 'غير معروف') if creds else 'غير معروف'
                raise Exception(
                    f"ليس لديك إذن للوصول إلى هذا الجدول. "
                    f"تأكد من مشاركته مع حساب الخدمة: {client_email}"
                )
            else:
                raise Exception(f"خطأ في الاتصال مع Google Sheets: {str(e)}")

    def get_available_sheets(self):
        if not self.service:
            self.initialize()
        try:
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.config.spreadsheet_id
            ).execute()
            sheets = []
            for sheet in spreadsheet.get('sheets', []):
                sheet_title = sheet.get('properties', {}).get('title', '')
                if sheet_title:
                    sheets.append(sheet_title)
            return sheets
        except Exception as e:
            logger.error(f"فشل في جلب قائمة الصفحات: {str(e)}")
            raise Exception(f"فشل في جلب قائمة الصفحات: {str(e)}")

    def get_sheet_data(self, sheet_name, import_all=True, start_row=None, end_row=None):
        if not self.service:
            self.initialize()

        try:
            from .google_sheets_utils import get_sheet_data_safe

            if not self.service or not self.config:
                raise Exception("لم يتم تهيئة الخدمة بشكل صحيح")

            # تحديد نطاق البيانات
            if not import_all:
                start_row = start_row or 1
                end_row = end_row or 1000
            else:
                start_row = None
                end_row = None

            # استخدام الدالة الآمنة لجلب البيانات
            values = get_sheet_data_safe(
                self.service,
                self.config.spreadsheet_id,
                sheet_name,
                start_row,
                end_row
            )

            return values

        except Exception as e:
            logger.error(f"فشل في جلب بيانات الصفحة {sheet_name}: {str(e)}")
            raise Exception(f"فشل في جلب البيانات: {str(e)}")

    def preview_data(self, sheet_name, max_rows=10):
        try:
            all_data = self.get_sheet_data(sheet_name)
            if not all_data:
                return {
                    'headers': [],
                    'data': [],
                    'total_rows': 0
                }
            headers = all_data[0] if all_data else []
            preview_data = all_data[1:max_rows+1] if len(all_data) > 1 else []
            return {
                'headers': headers,
                'data': preview_data,
                'total_rows': len(all_data) - 1
            }
        except Exception as e:
            logger.error(f"فشل في معاينة البيانات: {str(e)}")
            raise

    def import_data_by_type(self, sheet_name, data, clear_existing=False, user=None):
        """استيراد ديناميكي كامل لأي جدول بناءً على الأعمدة مع دعم حذف البيانات والعلاقات وتعيين حقول التواريخ"""
        if not data or not data[0]:
            return {
                'imported': 0,
                'updated': 0,
                'failed': 0,
                'errors': ['لا توجد بيانات للاستيراد']
            }
        from django.utils.dateparse import parse_datetime
        headers = data[0]
        rows = data[1:]
        # محاولة تحديد اسم الموديل من اسم الصفحة
        model_map = {
            'customers': ('customers', 'Customer'),
            'عملاء': ('customers', 'Customer'),
            'orders': ('orders', 'Order'),
            'طلبات': ('orders', 'Order'),
            'products': ('inventory', 'Product'),
            'منتجات': ('inventory', 'Product'),
            'users': ('accounts', 'User'),
            'مستخدمين': ('accounts', 'User'),
            'branches': ('accounts', 'Branch'),
            'فروع': ('accounts', 'Branch'),
            'databases': ('odoo_db_manager', 'Database'),
            'قواعد البيانات': ('odoo_db_manager', 'Database'),
            'inspections': ('inspections', 'Inspection'),
            'معاينات': ('inspections', 'Inspection'),
            'settings': ('accounts', 'CompanyInfo'),
            'إعدادات الشركة والنظام': ('accounts', 'CompanyInfo'),
        }
        sheet_lower = sheet_name.lower()
        model_info = None
        for key, val in model_map.items():
            if key in sheet_lower:
                model_info = val
                break
        if not model_info:
            return {
                'imported': 0,
                'updated': 0,
                'failed': len(rows),
                'errors': [f'لا يوجد موديل مطابق لاسم الصفحة: {sheet_name}']
            }
        app_label, model_name = model_info
        Model = apps.get_model(app_label, model_name)
        model_fields = {f.name: f for f in Model._meta.get_fields() if not f.auto_created}
        # حذف البيانات القديمة إذا طلب المستخدم ذلك
        if clear_existing:
            Model.objects.all().delete()
        imported = 0
        updated = 0
        failed = 0
        errors = []
        with transaction.atomic():
            for row_index, row in enumerate(rows, start=2):
                try:
                    obj_data = {}
                    date_fields_to_set = {}
                    for i, value in enumerate(row):
                        if i >= len(headers):
                            continue
                        field_label = headers[i].strip()
                        field_name = None
                        for mf in model_fields:
                            if mf.lower() == field_label.lower():
                                field_name = mf
                                break
                        if not field_name:
                            if field_label.endswith('_display'):
                                base_field = field_label.replace('_display', '')
                                if base_field in model_fields:
                                    field_name = base_field
                        if not field_name:
                            continue
                        field = model_fields[field_name]
                        # معالجة العلاقات ForeignKey (بما فيها التصنيف)
                        if field.is_relation and hasattr(field, 'related_model'):
                            RelatedModel = field.related_model
                            rel_obj = None
                            if value:
                                # جرب البحث بالاسم
                                try:
                                    rel_obj = RelatedModel.objects.filter(name=value).first()
                                except Exception:
                                    rel_obj = None
                                # جرب البحث بالكود أو أول CharField آخر إذا لم يوجد
                                if not rel_obj:
                                    for rel_field in RelatedModel._meta.fields:
                                        if rel_field.name != 'id' and rel_field.get_internal_type() == 'CharField':
                                            try:
                                                rel_obj = RelatedModel.objects.filter(**{rel_field.name: value}).first()
                                                if rel_obj:
                                                    break
                                            except Exception:
                                                continue
                                # إذا لم يوجد، أنشئ العنصر تلقائياً (مثلاً التصنيف)
                                if not rel_obj:
                                    try:
                                        rel_obj = RelatedModel.objects.create(name=value)
                                    except Exception:
                                        rel_obj = None
                            if rel_obj:
                                obj_data[field_name] = rel_obj
                        # معالجة حقول التواريخ (created_at, updated_at, ...إلخ)
                        elif field.get_internal_type() in ['DateTimeField', 'DateField']:
                            if value:
                                # حاول تحويل القيمة إلى datetime
                                dt_val = parse_datetime(value)
                                if not dt_val and field.get_internal_type() == 'DateField':
                                    try:
                                        from datetime import datetime
                                        dt_val = datetime.strptime(value, "%Y-%m-%d").date()
                                    except Exception:
                                        dt_val = None
                                if dt_val:
                                    date_fields_to_set[field_name] = dt_val
                        else:
                            obj_data[field_name] = value
                    # البحث عن كائن موجود (بناءً على الحقول الفريدة أو الاسم)
                    lookup_kwargs = {}
                    unique_fields = [f.name for f in Model._meta.fields if f.unique and f.name in obj_data]
                    if unique_fields:
                        for uf in unique_fields:
                            lookup_kwargs[uf] = obj_data[uf]
                    elif 'name' in obj_data:
                        lookup_kwargs['name'] = obj_data['name']
                    obj = None
                    if lookup_kwargs:
                        obj = Model.objects.filter(**lookup_kwargs).first()
                    if obj:
                        for k, v in obj_data.items():
                            setattr(obj, k, v)
                        obj.save()
                        # تحديث حقول التواريخ إذا وجدت
                        if date_fields_to_set:
                            for k, v in date_fields_to_set.items():
                                setattr(obj, k, v)
                            obj.save(update_fields=list(date_fields_to_set.keys()))
                        updated += 1
                    else:
                        obj = Model.objects.create(**obj_data)
                        # تحديث حقول التواريخ إذا وجدت
                        if date_fields_to_set:
                            for k, v in date_fields_to_set.items():
                                setattr(obj, k, v)
                            obj.save(update_fields=list(date_fields_to_set.keys()))
                        imported += 1
                except Exception as e:
                    errors.append(f"الصف {row_index}: {str(e)}")
                    failed += 1
                    logger.error(f"خطأ في استيراد {model_name} في الصف {row_index}: {str(e)}")
        return {
            'imported': imported,
            'updated': updated,
            'failed': failed,
            'errors': errors
        }
