"""
أمر تشخيص مشاكل المزامنة
"""
from django.core.management.base import BaseCommand
from odoo_db_manager.google_sync_advanced import GoogleSheetMapping
from odoo_db_manager.google_sheets_import import GoogleSheetsImporter


class Command(BaseCommand):
    help = 'تشخيص مشاكل المزامنة'

    def add_arguments(self, parser):
        parser.add_argument('--mapping-id', type=int, help='معرف التعيين للفحص')

    def handle(self, *args, **options):
        mapping_id = options.get('mapping_id')
        
        if mapping_id:
            self.diagnose_mapping(mapping_id)
        else:
            self.diagnose_all_mappings()

    def diagnose_mapping(self, mapping_id):
        """تشخيص تعيين محدد"""
        try:
            mapping = GoogleSheetMapping.objects.get(id=mapping_id)
            self.stdout.write(f"\n🔍 تشخيص التعيين: {mapping.name}")
            self.stdout.write(f"معرف الجدول: {mapping.spreadsheet_id}")
            self.stdout.write(f"اسم الصفحة: {mapping.sheet_name}")
            self.stdout.write(f"نشط: {'✅' if mapping.is_active else '❌'}")
            
            # فحص تعيينات الأعمدة
            column_mappings = mapping.get_column_mappings()
            self.stdout.write(f"\n📋 تعيينات الأعمدة ({len(column_mappings)}):")
            if column_mappings:
                for col, field in column_mappings.items():
                    self.stdout.write(f"  {col} → {field}")
            else:
                self.stdout.write("  ❌ لا توجد تعيينات أعمدة!")
                
            # فحص الإعدادات
            self.stdout.write(f"\n⚙️ إعدادات الإنشاء التلقائي:")
            self.stdout.write(f"  إنشاء عملاء: {'✅' if mapping.auto_create_customers else '❌'}")
            self.stdout.write(f"  إنشاء طلبات: {'✅' if mapping.auto_create_orders else '❌'}")
            self.stdout.write(f"  إنشاء معاينات: {'✅' if mapping.auto_create_inspections else '❌'}")
            self.stdout.write(f"  إنشاء تركيبات: {'✅' if mapping.auto_create_installations else '❌'}")
            self.stdout.write(f"  تحديث الموجود: {'✅' if mapping.update_existing else '❌'}")
            
            # فحص التحقق من صحة التعيينات
            errors = mapping.validate_mappings()
            if errors:
                self.stdout.write(f"\n❌ أخطاء في التعيين:")
                for error in errors:
                    self.stdout.write(f"  • {error}")
            else:
                self.stdout.write(f"\n✅ التعيين صحيح")
                
            # فحص الاتصال بـ Google Sheets
            self.stdout.write(f"\n🔗 فحص الاتصال بـ Google Sheets:")
            try:
                importer = GoogleSheetsImporter()
                importer.initialize()
                
                # حفظ المعرف الأصلي
                original_id = getattr(importer.config, 'spreadsheet_id', None)
                
                # تحديث معرف الجدول مؤقتاً
                if hasattr(importer.config, 'spreadsheet_id'):
                    importer.config.spreadsheet_id = mapping.spreadsheet_id
                
                try:
                    sheet_data = importer.get_sheet_data(mapping.sheet_name)
                    if sheet_data:
                        self.stdout.write(f"  ✅ تم جلب البيانات بنجاح")
                        self.stdout.write(f"  📊 عدد الصفوف: {len(sheet_data)}")
                        
                        # عرض عينة من البيانات
                        if len(sheet_data) >= mapping.header_row:
                            headers = sheet_data[mapping.header_row - 1]
                            self.stdout.write(f"  📋 العناوين: {headers[:5]}...")
                            
                            if len(sheet_data) >= mapping.start_row:
                                data_rows = sheet_data[mapping.start_row - 1:]
                                self.stdout.write(f"  📄 صفوف البيانات: {len(data_rows)}")
                                
                                # عرض أول صف من البيانات
                                if data_rows:
                                    first_row = data_rows[0]
                                    self.stdout.write(f"  🔍 أول صف: {first_row[:3]}...")
                            else:
                                self.stdout.write(f"  ❌ لا توجد صفوف بيانات (start_row: {mapping.start_row})")
                        else:
                            self.stdout.write(f"  ❌ لا توجد عناوين (header_row: {mapping.header_row})")
                    else:
                        self.stdout.write(f"  ❌ لا توجد بيانات في الجدول")
                        
                finally:
                    # استعادة المعرف الأصلي
                    if original_id and hasattr(importer.config, 'spreadsheet_id'):
                        importer.config.spreadsheet_id = original_id
                        
            except Exception as e:
                self.stdout.write(f"  ❌ خطأ في الاتصال: {str(e)}")
                
            # اقتراحات للإصلاح
            self.stdout.write(f"\n💡 اقتراحات:")
            if not column_mappings:
                self.stdout.write("  • قم بإعداد تعيينات الأعمدة أولاً")
            if not mapping.auto_create_orders:
                self.stdout.write("  • فعّل 'إنشاء طلبات تلقائياً'")
            if not mapping.auto_create_customers:
                self.stdout.write("  • فعّل 'إنشاء عملاء تلقائياً'")
            if errors:
                self.stdout.write("  • أصلح أخطاء التعيين المذكورة أعلاه")
                
        except GoogleSheetMapping.DoesNotExist:
            self.stdout.write(f"❌ لم يتم العثور على تعيين بالمعرف: {mapping_id}")
        except Exception as e:
            self.stdout.write(f"❌ خطأ: {str(e)}")

    def diagnose_all_mappings(self):
        """تشخيص جميع التعيينات"""
        mappings = GoogleSheetMapping.objects.all()
        
        if not mappings.exists():
            self.stdout.write("❌ لا توجد تعيينات في النظام")
            return
            
        self.stdout.write(f"📋 إجمالي التعيينات: {mappings.count()}")
        
        for mapping in mappings:
            self.stdout.write(f"\n{mapping.id}. {mapping.name}")
            self.stdout.write(f"   نشط: {'✅' if mapping.is_active else '❌'}")
            self.stdout.write(f"   تعيينات: {'✅' if mapping.get_column_mappings() else '❌'}")
            self.stdout.write(f"   إنشاء طلبات: {'✅' if mapping.auto_create_orders else '❌'}")
