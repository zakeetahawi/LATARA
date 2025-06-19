"""
وجهات نظر إدارة قواعد البيانات على طراز أودو
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponse, JsonResponse, FileResponse
from django.utils import timezone
from django.conf import settings
from django.db.models import Q
import os
import datetime
import shutil

from .models import Database, Backup, BackupSchedule, GoogleDriveConfig
from .services.database_service import DatabaseService
# تم إزالة BackupService لتجنب التضارب
from .services.scheduled_backup_service import scheduled_backup_service
from .forms import BackupScheduleForm, GoogleDriveConfigForm, DatabaseForm

def is_staff_or_superuser(user):
    """التحقق من أن المستخدم موظف أو مدير"""
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_staff_or_superuser)
def dashboard(request):
    """عرض لوحة التحكم الرئيسية"""
    # تحديث حالة الاتصال لجميع قواعد البيانات
    database_service = DatabaseService()
    databases = Database.objects.all().order_by('-is_active', '-created_at')
    
    # تحديث حالة الاتصال لكل قاعدة بيانات
    for db in databases:
        try:
            success, message = database_service.test_connection(db.connection_info)
            db.status = success
            if not success:
                db.error_message = message
            else:
                db.error_message = ""
            db.save()
        except Exception as e:
            db.status = False
            db.error_message = str(e)
            db.save()

    # محاولة اكتشاف قواعد البيانات الموجودة في PostgreSQL
    try:
        discovered_databases = database_service.discover_postgresql_databases()
        # سنعرض هذه في context لإظهارها للمستخدم
    except Exception as e:
        discovered_databases = []
        print(f"خطأ في اكتشاف قواعد البيانات: {e}")

    # الحصول على النسخ الاحتياطية
    backups = Backup.objects.all().order_by('-created_at')[:10]

    # حساب إجمالي حجم النسخ الاحتياطية
    total_size = sum(backup.size for backup in Backup.objects.all())

    # تحويل الحجم إلى وحدة مناسبة
    total_size_display = "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if total_size < 1024.0:
            total_size_display = f"{total_size:.1f} {unit}"
            break
        total_size /= 1024.0
    else:
        total_size_display = f"{total_size:.1f} TB"

    # الحصول على آخر نسخة احتياطية
    last_backup = Backup.objects.order_by('-created_at').first()

    # التحقق من وجود رسالة نجاح لتنشيط قاعدة البيانات
    show_activation_success = request.session.pop('show_db_activation_success', False)
    activated_db_name = request.session.pop('activated_db_name', '')
    created_default_user = request.session.pop('created_default_user', False)
    
    # الحصول على معلومات قاعدة البيانات الحالية من إعدادات Django
    from django.conf import settings
    current_db_name = settings.DATABASES['default']['NAME']
    current_db_user = settings.DATABASES['default']['USER']
    current_db_host = settings.DATABASES['default']['HOST']
    current_db_port = settings.DATABASES['default']['PORT']
    current_db_password = settings.DATABASES['default']['PASSWORD']
    
    # البحث عن قاعدة البيانات الحالية في قائمة قواعد البيانات
    current_database = None
    for db in databases:
        if db.connection_info.get('NAME') == current_db_name:
            current_database = db
            break
    
    # إذا لم يتم العثور على قاعدة البيانات الحالية، نقوم بإنشائها
    if not current_database:
        try:
            # إنشاء قاعدة بيانات جديدة للقاعدة الحالية
            current_database = Database(
                name=f"قاعدة البيانات الحالية ({current_db_name})",
                db_type='postgresql',
                connection_info={
                    'ENGINE': 'django.db.backends.postgresql',
                    'NAME': current_db_name,
                    'USER': current_db_user,
                    'PASSWORD': current_db_password,
                    'HOST': current_db_host,
                    'PORT': current_db_port,
                }
            )
            current_database.save()
            print(f"تم إنشاء قاعدة البيانات الحالية: {current_db_name}")
        except Exception as e:
            print(f"حدث خطأ أثناء إنشاء قاعدة البيانات الحالية: {str(e)}")
    
    # الحصول على قاعدة البيانات النشطة
    active_database = databases.filter(is_active=True).first()
    
    # إذا كانت قاعدة البيانات الحالية موجودة ولكنها غير نشطة، نقوم بتنشيطها
    if current_database and not current_database.is_active:
        # تعطيل جميع قواعد البيانات الأخرى
        Database.objects.exclude(id=current_database.id).update(is_active=False)
        # تنشيط قاعدة البيانات الحالية
        current_database.is_active = True
        current_database.save()
        active_database = current_database
        print(f"تم تنشيط قاعدة البيانات الحالية: {current_db_name}")
    
    # التحقق من حالة الاتصال بقاعدة البيانات الحالية
    current_db_status = False
    try:
        import psycopg2
        conn = psycopg2.connect(
            dbname=current_db_name,
            user=current_db_user,
            password=current_db_password,
            host=current_db_host,
            port=current_db_port,
            connect_timeout=3
        )
        conn.close()
        current_db_status = True
    except Exception as e:
        print(f"فشل الاتصال بقاعدة البيانات الحالية: {str(e)}")
        pass

    context = {
        'databases': databases,        'backups': backups,
        'total_size_display': total_size_display,
        'last_backup': last_backup,
        'title': _('إدارة قواعد البيانات'),
        'show_activation_success': show_activation_success,
        'activated_db_name': activated_db_name,
        'created_default_user': created_default_user,
        'active_database': active_database,
        'current_db_name': current_db_name,
        'current_db_user': current_db_user,
        'current_db_host': current_db_host,
        'current_db_port': current_db_port,
        'current_db_status': current_db_status,
        'discovered_databases': discovered_databases,  # قواعد البيانات الموجودة في PostgreSQL
    }

    return render(request, 'odoo_db_manager/dashboard.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
def database_list(request):
    """عرض قائمة قواعد البيانات"""
    # الحصول على قواعد البيانات
    databases = Database.objects.all().order_by('-is_active', '-created_at')

    # التحقق من وجود رسالة نجاح لتنشيط قاعدة البيانات
    show_activation_success = request.session.pop('show_activation_success', False)
    activated_db_name = request.session.pop('activated_db_name', '')

    context = {
        'databases': databases,
        'title': _('قائمة قواعد البيانات'),
        'show_activation_success': show_activation_success,
        'activated_db_name': activated_db_name,
    }

    return render(request, 'odoo_db_manager/database_list.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
def database_discover(request):
    """اكتشاف قواعد البيانات الموجودة في PostgreSQL"""
    if request.method == 'POST':
        try:
            # اكتشاف ومزامنة قواعد البيانات
            database_service = DatabaseService()
            database_service.sync_discovered_databases()

            messages.success(request, _('تم اكتشاف ومزامنة قواعد البيانات بنجاح.'))
        except Exception as e:
            messages.error(request, _(f'حدث خطأ أثناء اكتشاف قواعد البيانات: {str(e)}'))

        return redirect('odoo_db_manager:database_list')

    # عرض قواعد البيانات المكتشفة قبل المزامنة
    try:
        database_service = DatabaseService()
        discovered_dbs = database_service.discover_postgresql_databases()

        # التحقق من قواعد البيانات الموجودة في النظام
        existing_dbs = Database.objects.filter(db_type='postgresql').values_list('name', flat=True)

        # تصنيف قواعد البيانات
        new_dbs = []
        existing_in_system = []

        for db_info in discovered_dbs:
            if db_info['name'] in existing_dbs:
                existing_in_system.append(db_info)
            else:
                new_dbs.append(db_info)

        context = {
            'discovered_dbs': discovered_dbs,
            'new_dbs': new_dbs,
            'existing_in_system': existing_in_system,
            'title': _('اكتشاف قواعد البيانات'),
        }

    except Exception as e:
        messages.error(request, _(f'حدث خطأ أثناء اكتشاف قواعد البيانات: {str(e)}'))
        context = {
            'discovered_dbs': [],
            'new_dbs': [],
            'existing_in_system': [],
            'title': _('اكتشاف قواعد البيانات'),
        }

    return render(request, 'odoo_db_manager/database_discover.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
def database_detail(request, pk):
    """عرض تفاصيل قاعدة البيانات"""
    # الحصول على قاعدة البيانات
    database = get_object_or_404(Database, pk=pk)    # الحصول على النسخ الاحتياطية
    backups = database.backups.all().order_by('-created_at')    # التحقق من رسائل نجاح إنشاء قاعدة البيانات
    database_created_success = request.session.pop('database_created_success', False)
    created_database_name = request.session.pop('created_database_name', '')
    default_user_created = request.session.pop('default_user_created', False)
    migrations_applied = request.session.pop('migrations_applied', False)

    context = {
        'database': database,
        'backups': backups,
        'title': _('تفاصيل قاعدة البيانات'),
        'database_created_success': database_created_success,
        'created_database_name': created_database_name,
        'default_user_created': default_user_created,
        'migrations_applied': migrations_applied,
    }

    return render(request, 'odoo_db_manager/database_detail.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
@login_required
@user_passes_test(is_staff_or_superuser)
def database_create(request):
    """إنشاء قاعدة بيانات جديدة"""
    if request.method == 'POST':
        form = DatabaseForm(request.POST)
        if form.is_valid():
            try:                # حفظ قاعدة البيانات من النموذج (بدون إنشاء قاعدة البيانات الفعلية)
                database = form.save(commit=False)
                
                # إنشاء قاعدة البيانات الفعلية إذا أراد المستخدم ذلك
                force_create = request.POST.get('force_create') == 'on'
                ignore_db_errors = request.POST.get('ignore_db_errors') == 'on'
                create_actual_db = request.POST.get('create_actual_db') == 'on'                  # حفظ السجل أولاً
                database.save()
                  # إنشاء خدمة قاعدة البيانات مرة واحدة
                database_service = DatabaseService()
                
                if create_actual_db and not ignore_db_errors:
                    # استخدام خدمة إنشاء قواعد البيانات لإنشاء قاعدة البيانات الفعلية
                    try:
                        # إنشاء قاعدة البيانات الفعلية
                        db_created, create_message = database_service.create_physical_database(
                            connection_info=database.connection_info,
                            force_create=force_create
                        )
                        
                        if db_created:
                            # اختبار الاتصال بعد الإنشاء
                            success, test_message = database_service.test_connection(database.connection_info)
                            
                            if success:
                                database.status = True
                                database.error_message = ''
                                database.save()
                                
                                # تطبيق migrations في قاعدة البيانات الجديدة
                                migrations_applied = False
                                try:
                                    migrations_applied = _apply_migrations_to_database(database)
                                except Exception as migrate_error:
                                    print(f"خطأ في تطبيق migrations: {migrate_error}")
                                  # محاولة إنشاء مستخدم افتراضي فقط إذا تم تطبيق migrations
                                default_user_created = False
                                if migrations_applied:
                                    # انتظار قصير لضمان اكتمال migrations
                                    import time
                                    time.sleep(2)
                                    
                                    try:
                                        default_user_created = _create_default_user(database)
                                    except Exception as user_error:
                                        print(f"خطأ في إنشاء المستخدم الافتراضي: {user_error}")
                                        # محاولة ثانية بعد انتظار أطول
                                        try:
                                            time.sleep(3)
                                            default_user_created = _create_default_user(database)
                                        except Exception as user_error2:
                                            print(f"فشل في المحاولة الثانية لإنشاء المستخدم الافتراضي: {user_error2}")
                                
                                # حفظ معلومات نجاح الإنشاء في الجلسة لعرضها في SweetAlert
                                request.session['database_created_success'] = True
                                request.session['created_database_name'] = database.name
                                request.session['created_database_id'] = database.id
                                request.session['default_user_created'] = default_user_created
                                request.session['migrations_applied'] = migrations_applied
                                
                                success_msg = f'تم إنشاء قاعدة البيانات في PostgreSQL وتم اختبار الاتصال بنجاح. {create_message}'
                                if migrations_applied:
                                    success_msg += " تم تطبيق migrations."
                                if default_user_created:
                                    success_msg += " تم إنشاء مستخدم افتراضي."
                                
                                messages.success(request, success_msg)
                            else:
                                database.status = False
                                database.error_message = test_message
                                database.save()
                                messages.warning(request, f'تم إنشاء قاعدة البيانات في PostgreSQL ولكن فشل اختبار الاتصال: {test_message}')
                        else:
                            database.status = False
                            database.error_message = create_message
                            database.save()
                            messages.error(request, f'فشل في إنشاء قاعدة البيانات: {create_message}')
                    
                    except Exception as e:
                        database.status = False
                        database.error_message = str(e)
                        database.save()
                        messages.error(request, f'حدث خطأ أثناء إنشاء قاعدة البيانات: {str(e)}')
                
                elif not create_actual_db and not ignore_db_errors:
                    # فقط اختبار الاتصال بدون إنشاء قاعدة البيانات
                    success, message = database_service.test_connection(database.connection_info)
                    
                    if success:
                        database.status = True
                        database.error_message = ''
                        database.save()
                        messages.success(request, f'تم إنشاء سجل قاعدة البيانات وتم اختبار الاتصال بقاعدة البيانات الموجودة. {message}')
                    else:
                        database.status = False
                        database.error_message = message
                        database.save()
                        messages.warning(request, f'تم إنشاء سجل قاعدة البيانات ولكن فشل اختبار الاتصال: {message}')
                else:
                    # تجاهل اختبار الاتصال
                    messages.warning(request, 'تم إنشاء سجل قاعدة البيانات دون اختبار الاتصال أو إنشاء قاعدة البيانات.')
                
                return redirect('odoo_db_manager:database_detail', pk=database.pk)
                
            except Exception as e:
                messages.error(request, _(f'حدث خطأ أثناء إنشاء قاعدة البيانات: {str(e)}'))
        else:
            # إضافة رسائل الأخطاء للمستخدم
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label}: {error}")
    else:
        form = DatabaseForm()

    context = {
        'title': _('إنشاء قاعدة بيانات جديدة'),
        'form': form,
    }

    return render(request, 'odoo_db_manager/database_form.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
def database_activate(request, pk):
    """تنشيط قاعدة بيانات"""
      # التأكد من أن الطلب POST فقط أو AJAX GET
    if request.method == 'GET':
        # إذا كان GET request، إعادة توجيه إلى dashboard مع رسالة
        messages.warning(request, 'يرجى استخدام زر التفعيل من لوحة التحكم.')
        return redirect('odoo_db_manager:dashboard')
    
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'طريقة الطلب غير صحيحة. يجب استخدام POST.'
        })
    
    try:
        # الحصول على قاعدة البيانات
        print(f"محاولة تنشيط قاعدة البيانات بمعرف: {pk}")
        database = get_object_or_404(Database, pk=pk)
        print(f"تم العثور على قاعدة البيانات: {database.name}")
        
        # تنشيط قاعدة البيانات باستخدام الطريقة الجديدة
        print("بدء عملية تنشيط قاعدة البيانات...")
        activation_result = database.activate()
        print(f"نتيجة التنشيط: {activation_result}")
        
        if activation_result.get('success', False):
            print("تم تنشيط قاعدة البيانات بنجاح، محاولة إنشاء مستخدم افتراضي...")
            
            # محاولة إنشاء مستخدم افتراضي إذا لم يكن هناك مستخدمين
            try:
                created_default_user = database.create_default_user()
                print(f"نتيجة إنشاء المستخدم الافتراضي: {created_default_user}")
            except Exception as user_error:
                print(f"خطأ في إنشاء المستخدم الافتراضي: {str(user_error)}")
                created_default_user = False
              # استخدام رسالة نجاح مع معلومات إضافية
            success_message = f'تم تنشيط قاعدة البيانات {database.name} بنجاح.'
            messages.success(request, success_message)
            
            # لا نحفظ في session لتجنب مشاكل تغيير قاعدة البيانات
            # request.session['show_db_activation_success'] = True
            # request.session['activated_db_name'] = database.name
            # request.session['created_default_user'] = created_default_user
            
            # إعادة توجيه مع رسالة تطلب إعادة التشغيل
            response_data = {
                'success': True, 
                'message': 'تم تنشيط قاعدة البيانات وتطبيق التغييرات بنجاح',
                'database_name': activation_result.get('database_name', database.name),
                'created_default_user': created_default_user,
                'requires_restart': activation_result.get('requires_restart', False)
            }
            print(f"إعادة الاستجابة: {response_data}")
            
            response = JsonResponse(response_data)
            response['Content-Type'] = 'application/json; charset=utf-8'
            return response
        else:
            error_message = activation_result.get('message', f'حدث خطأ أثناء تنشيط قاعدة البيانات {database.name}.')
            print(f"فشل التنشيط: {error_message}")
            
            response = JsonResponse({
                'success': False,
                'message': error_message
            })
            response['Content-Type'] = 'application/json; charset=utf-8'
            return response
    
    except Exception as e:
        print(f"خطأ عام في database_activate: {str(e)}")
        import traceback
        print(f"تفاصيل الخطأ: {traceback.format_exc()}")
        
        return JsonResponse({
            'success': False,
            'message': f'حدث خطأ أثناء تنشيط قاعدة البيانات: {str(e)}'
        })

@login_required
@user_passes_test(is_staff_or_superuser)
def database_delete(request, pk):
    """حذف قاعدة بيانات"""
    # الحصول على قاعدة البيانات
    database = get_object_or_404(Database, pk=pk)

    if request.method == 'POST':
        try:
            # حذف قاعدة البيانات
            database_service = DatabaseService()
            database_service.delete_database(database.id)

            messages.success(request, _('تم حذف قاعدة البيانات بنجاح.'))
            return redirect('odoo_db_manager:database_list')
        except Exception as e:
            messages.error(request, _(f'حدث خطأ أثناء حذف قاعدة البيانات: {str(e)}'))
            return redirect('odoo_db_manager:database_detail', pk=database.pk)

    context = {
        'database': database,
        'title': _('حذف قاعدة بيانات'),
    }

    return render(request, 'odoo_db_manager/database_delete.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
def backup_create(request, database_id=None):
    """إنشاء نسخة احتياطية"""
    import os
    import shutil
    import datetime
    
    # الحصول على قاعدة البيانات
    database = None
    if database_id:
        database = get_object_or_404(Database, pk=database_id)

    if request.method == 'POST':
        # الحصول على بيانات النموذج
        database_id = request.POST.get('database_id', database_id)
        name = request.POST.get('name', '')
        backup_type = request.POST.get('backup_type', 'full')

        try:
            # طباعة معلومات تشخيصية
            print(f"إنشاء نسخة احتياطية جديدة")
            print(f"معرف قاعدة البيانات: {database_id}")
            print(f"اسم النسخة الاحتياطية: {name}")
            print(f"نوع النسخة الاحتياطية: {backup_type}")

            # الحصول على قاعدة البيانات
            db = Database.objects.get(id=database_id)
            print(f"معلومات قاعدة البيانات: {db.name}, {db.db_type}, {db.connection_info}")

            # التأكد من وجود كلمة المرور الصحيحة
            if db.db_type == 'postgresql' and (not db.connection_info.get('PASSWORD') or db.connection_info.get('PASSWORD') != '5525'):
                # تحديث كلمة المرور
                connection_info = db.connection_info
                connection_info['PASSWORD'] = '5525'
                db.connection_info = connection_info
                db.save()
                print(f"تم تحديث كلمة المرور لقاعدة البيانات: {db.name}")

            # إنشاء نسخة احتياطية بسيطة عن طريق نسخ ملف قاعدة البيانات SQLite مباشرة
            if settings.DATABASES['default']['ENGINE'].endswith('sqlite3'):

                # الحصول على مسار ملف قاعدة البيانات
                db_file = settings.DATABASES['default']['NAME']
                print(f"مسار ملف قاعدة البيانات: {db_file}")

                # إنشاء اسم النسخة الاحتياطية إذا لم يتم توفيره
                if not name:
                    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    name = f"{db.name}_{backup_type}_{timestamp}"

                # إنشاء مجلد النسخ الاحتياطي إذا لم يكن موجود
                backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
                os.makedirs(backup_dir, exist_ok=True)

                # إنشاء مسار ملف النسخة الاحتياطية
                backup_file = os.path.join(backup_dir, f"{name}.sqlite3")
                print(f"مسار ملف النسخة الاحتياطية: {backup_file}")

                # نسخ ملف قاعدة البيانات
                shutil.copy2(db_file, backup_file)
                print(f"تم نسخ ملف قاعدة البيانات بنجاح إلى: {backup_file}")

                # إنشاء سجل النسخة الاحتياطية في قاعدة البيانات
                backup = Backup.objects.create(
                    name=name,
                    database=db,
                    backup_type=backup_type,
                    file_path=backup_file,
                    created_by=request.user
                )
                print(f"تم إنشاء سجل النسخة الاحتياطية بنجاح: {backup.id}")
            else:
                # إنشاء النسخة الاحتياطية لقاعدة بيانات PostgreSQL
                if not name:
                    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    name = f"{db.name}_{backup_type}_{timestamp}"

                # إنشاء مجلد النسخ الاحتياطي إذا لم يكن موجود
                backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
                os.makedirs(backup_dir, exist_ok=True)

                # إنشاء ملف JSON باستخدام Django dumpdata
                backup_file = os.path.join(backup_dir, f"{name}.json")
                print(f"🔄 إنشاء نسخة احتياطية JSON: {backup_file}")

                try:
                    # استخدام Django dumpdata لإنشاء النسخة الاحتياطية
                    from django.core.management import call_command
                    from io import StringIO

                    # إنشاء buffer لحفظ البيانات
                    output = StringIO()

                    # تحديد التطبيقات المراد نسخها حسب نوع النسخة الاحتياطية
                    if backup_type == 'customers':
                        apps_to_backup = ['customers']
                    elif backup_type == 'users':
                        apps_to_backup = ['auth', 'accounts']
                    elif backup_type == 'settings':
                        apps_to_backup = ['odoo_db_manager']
                    else:  # full
                        apps_to_backup = ['customers', 'orders', 'inspections', 'inventory', 'installations', 'factory', 'accounts', 'odoo_db_manager']                    # تنفيذ dumpdata مع معالجة مشاكل الترميز
                    import os
                    import tempfile
                    
                    # إنشاء ملف مؤقت
                    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.json') as temp_file:
                        temp_path = temp_file.name
                    
                    try:
                        # تنفيذ dumpdata إلى ملف مؤقت مباشرة
                        with open(temp_path, 'w', encoding='utf-8') as temp_output:
                            call_command('dumpdata', *apps_to_backup, stdout=temp_output, 
                                       format='json', indent=2, verbosity=0)
                        
                        # نسخ من الملف المؤقت إلى الملف النهائي
                        with open(temp_path, 'r', encoding='utf-8') as temp_input:
                            with open(backup_file, 'w', encoding='utf-8') as final_output:
                                final_output.write(temp_input.read())
                    
                    finally:
                        # حذف الملف المؤقت
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)

                    print(f"تم إنشاء ملف النسخة الاحتياطية: {backup_file}")
                    print(f"حجم الملف: {os.path.getsize(backup_file)} بايت")

                    # إنشاء سجل النسخة الاحتياطية في قاعدة البيانات
                    backup = Backup.objects.create(
                        name=name,
                        database=db,
                        backup_type=backup_type,
                        file_path=backup_file,
                        size=os.path.getsize(backup_file),
                        created_by=request.user
                    )
                    print(f"تم إنشاء سجل النسخة الاحتياطية بنجاح: {backup.id}")

                except Exception as backup_error:
                    print(f"خطأ في إنشاء النسخة الاحتياطية: {str(backup_error)}")
                    # في حالة الفشل، إنشاء سجل بدون ملف
                    backup = Backup.objects.create(
                        name=name,
                        database=db,
                        backup_type=backup_type,
                        file_path="",
                        created_by=request.user
                    )
                    raise backup_error

            messages.success(request, _('تم إنشاء النسخة الاحتياطية بنجاح.'))
            return redirect('odoo_db_manager:backup_detail', pk=backup.pk)
        except Exception as e:
            messages.error(request, _(f'حدث خطأ أثناء إنشاء النسخة الاحتياطية: {str(e)}'))
            return redirect('odoo_db_manager:backup_create')

    # الحصول على قواعد البيانات
    databases = Database.objects.all()

    # الحصول على أنواع النسخ الاحتياطية من نموذج Backup
    backup_types = Backup.BACKUP_TYPES

    context = {
        'database': database,
        'databases': databases,
        'backup_types': backup_types,
        'title': _('إنشاء نسخة احتياطية جديدة'),
    }

    return render(request, 'odoo_db_manager/backup_form.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
def backup_detail(request, pk):
    """عرض تفاصيل النسخة الاحتياطية"""
    # الحصول على النسخة الاحتياطية
    backup = get_object_or_404(Backup, pk=pk)

    context = {
        'backup': backup,
        'title': _('تفاصيل النسخة الاحتياطية'),
    }

    return render(request, 'odoo_db_manager/backup_detail.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
def backup_restore(request, pk):
    """استعادة النسخة الاحتياطية"""
    # الحصول على النسخة الاحتياطية
    backup = get_object_or_404(Backup, pk=pk)

    # حفظ معلومات النسخة الاحتياطية قبل استعادتها
    backup_info = {
        'id': backup.id,
        'name': backup.name,
        'database_id': backup.database.id,
        'backup_type': backup.backup_type,
        'file_path': backup.file_path,
        'created_at': backup.created_at,
        'created_by_id': backup.created_by.id if backup.created_by else None
    }

    if request.method == 'POST':
        # الحصول على خيار حذف البيانات القديمة
        clear_data = request.POST.get('clear_data', 'off') == 'on'

        try:
            # التحقق من وجود الملف
            if not os.path.exists(backup.file_path):
                raise FileNotFoundError(f"ملف النسخة الاحتياطية '{backup.file_path}' غير موجود")

            # إذا كان ملف SQLite3، نقوم باستعادته مباشرة
            if backup.file_path.endswith('.sqlite3'):
                # الحصول على مسار ملف قاعدة البيانات الحالية
                db_file = settings.DATABASES['default']['NAME']

                # إنشاء نسخة احتياطية من قاعدة البيانات الحالية قبل الاستبدال
                backup_current_db = f"{db_file}.bak"
                shutil.copy2(db_file, backup_current_db)

                try:
                    # نسخ ملف النسخة الاحتياطية إلى مسار قاعدة البيانات الحالية
                    shutil.copy2(backup.file_path, db_file)

                    # إعادة إنشاء سجل النسخة الاحتياطية بعد استعادة قاعدة البيانات
                    from accounts.models import User

                    # الحصول على قاعدة البيانات
                    try:
                        db = Database.objects.get(id=backup_info['database_id'])
                    except Database.DoesNotExist:
                        # إذا لم تكن قاعدة البيانات موجودة، نستخدم أول قاعدة بيانات متاحة
                        db = Database.objects.first()
                        if not db:
                            # إذا لم تكن هناك قواعد بيانات، نقوم بإنشاء واحدة
                            db = Database.objects.create(
                                name="Default Database",
                                db_type="sqlite3",
                                connection_info={}
                            )

                    # الحصول على المستخدم
                    user_id = backup_info['created_by_id']
                    user = None
                    if user_id:
                        try:
                            user = User.objects.get(id=user_id)
                        except User.DoesNotExist:
                            # إذا لم يكن المستخدم موجودًا، نستخدم أول مستخدم متاح
                            user = User.objects.first()

                    # إعادة إنشاء سجل النسخة الاحتياطية
                    try:
                        Backup.objects.get(id=backup_info['id'])
                    except Backup.DoesNotExist:
                        Backup.objects.create(
                            id=backup_info['id'],
                            name=backup_info['name'],
                            database=db,
                            backup_type=backup_info['backup_type'],
                            file_path=backup_info['file_path'],
                            created_at=backup_info['created_at'],
                            created_by=user
                        )

                    messages.success(request, _('تم استعادة النسخة الاحتياطية بنجاح.'))
                except Exception as e:
                    # استعادة النسخة الاحتياطية في حالة حدوث خطأ
                    shutil.copy2(backup_current_db, db_file)
                    raise RuntimeError(f"فشل استعادة قاعدة البيانات: {str(e)}")
                finally:
                    # حذف النسخة الاحتياطية المؤقتة
                    if os.path.exists(backup_current_db):
                        os.unlink(backup_current_db)
            else:                # استعادة النسخة الاحتياطية بطريقة مبسطة
                # تم إزالة BackupService لتجنب التعقيدات
                result = None
                if backup.file_path.endswith('.json'):
                    result = _restore_json_simple(backup.file_path, clear_existing=clear_data)
                elif backup.file_path.endswith('.json.gz'):
                    # التعامل مع الملفات المضغوطة
                    import gzip
                    import tempfile

                    print(f"📦 ملف مضغوط - فك الضغط: {backup.file_path}")

                    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as temp_file:
                        temp_path = temp_file.name

                    try:
                        # فك ضغط الملف
                        with gzip.open(backup.file_path, 'rt', encoding='utf-8') as gz_file:
                            content = gz_file.read()

                        # كتابة المحتوى المفكوك
                        with open(temp_path, 'w', encoding='utf-8') as json_file:
                            json_file.write(content)

                        print(f"✅ تم فك الضغط بنجاح إلى: {temp_path}")

                        # استعادة من الملف المفكوك
                        result = _restore_json_simple(temp_path, clear_existing=clear_data)

                    finally:
                        # حذف الملف المؤقت
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                            print(f"🗑️ تم حذف الملف المؤقت: {temp_path}")
                else:
                    raise ValueError("نوع ملف غير مدعوم. يرجى استخدام ملفات JSON أو JSON.GZ.")
                
                # إنشاء رسالة تفصيلية
                if result:
                    success_count = result.get('success_count', 0)
                    error_count = result.get('error_count', 0)
                    total_count = result.get('total_count', 0)
                    
                    if error_count == 0:
                        success_message = f"🎉 تم استعادة جميع البيانات بنجاح!\n\n📊 الإحصائيات:\n• إجمالي العناصر: {total_count}\n• تم الاستعادة: {success_count}\n• نسبة النجاح: 100%"
                    else:
                        success_rate = (success_count / total_count * 100) if total_count > 0 else 0
                        success_message = f"✅ تمت الاستعادة بنجاح!\n\n📊 الإحصائيات:\n• إجمالي العناصر: {total_count}\n• تم الاستعادة: {success_count}\n• فشل: {error_count}\n• نسبة النجاح: {success_rate:.1f}%"
                        
                        if error_count > 0:
                            success_message += f"\n\n⚠️ تحذير: {error_count} عنصر لم يتم استعادته (عادة بسبب بيانات غير متوافقة مع النسخة الحالية)."
                    
                    messages.success(request, success_message)
                else:
                    messages.success(request, _('تم استعادة النسخة الاحتياطية بنجاح.'))

            return redirect('odoo_db_manager:dashboard')
        except Exception as e:
            messages.error(request, _(f'حدث خطأ أثناء استعادة النسخة الاحتياطية: {str(e)}'))
            try:
                # محاولة الوصول إلى صفحة تفاصيل النسخة الاحتياطية
                return redirect('odoo_db_manager:backup_detail', pk=backup.pk)
            except:
                # إذا لم يكن سجل النسخة الاحتياطية موجودًا، نعود إلى لوحة التحكم
                return redirect('odoo_db_manager:dashboard')

    context = {
        'backup': backup,
        'title': _('استعادة النسخة الاحتياطية'),
    }

    return render(request, 'odoo_db_manager/backup_restore.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
def backup_delete(request, pk):
    """حذف النسخة الاحتياطية"""
    # الحصول على النسخة الاحتياطية
    backup = get_object_or_404(Backup, pk=pk)

    if request.method == 'POST':
        try:
            # حذف النسخة الاحتياطية بطريقة مبسطة
            # حذف الملف إذا كان موجوداً
            if backup.file_path and os.path.exists(backup.file_path):
                os.unlink(backup.file_path)

            # حذف السجل من قاعدة البيانات
            backup.delete()

            messages.success(request, _('تم حذف النسخة الاحتياطية بنجاح.'))
            return redirect('odoo_db_manager:dashboard')
        except Exception as e:
            messages.error(request, _(f'حدث خطأ أثناء حذف النسخة الاحتياطية: {str(e)}'))
            return redirect('odoo_db_manager:backup_detail', pk=backup.pk)

    context = {
        'backup': backup,
        'title': _('حذف النسخة الاحتياطية'),
    }

    return render(request, 'odoo_db_manager/backup_delete.html', context)

@login_required
@user_passes_test(is_staff_or_superuser)
def backup_download(request, pk):
    """تحميل ملف النسخة الاحتياطية"""
    # الحصول على النسخة الاحتياطية
    backup = get_object_or_404(Backup, pk=pk)

    # التحقق من وجود الملف
    if not os.path.exists(backup.file_path):
        messages.error(request, _('ملف النسخة الاحتياطية غير موجود.'))
        return redirect('odoo_db_manager:backup_detail', pk=backup.pk)

    # إنشاء استجابة الملف
    response = FileResponse(open(backup.file_path, 'rb'))
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(backup.file_path)}"'

    return response

@login_required
@user_passes_test(is_staff_or_superuser)
def backup_upload(request, database_id=None):
    """استعادة من ملف تم تحميله"""
    # الحصول على قاعدة البيانات
    database = None
    if database_id:
        database = get_object_or_404(Database, pk=database_id)

    if request.method == 'POST':
        # التحقق من وجود قاعدة بيانات
        database_id = request.POST.get('database_id', database_id)
        if not database_id:
            messages.error(request, _('يرجى اختيار قاعدة بيانات.'))
            return redirect('odoo_db_manager:backup_upload')

        # التحقق من وجود ملف
        if 'backup_file' not in request.FILES or not request.FILES['backup_file']:
            messages.error(request, _('يرجى اختيار ملف النسخة الاحتياطية.'))
            return redirect('odoo_db_manager:backup_upload')

        # التحقق من أن الملف ليس فارغاً
        uploaded_file = request.FILES['backup_file']
        if uploaded_file.size == 0:
            messages.error(request, _('الملف المرفوع فارغ. يرجى اختيار ملف صالح.'))
            return redirect('odoo_db_manager:backup_upload')

        # الحصول على خيارات الاستعادة
        backup_type = request.POST.get('backup_type', 'full')
        clear_data = request.POST.get('clear_data', 'off') == 'on'

        try:
            print("🚀 بدء عملية الاستعادة المباشرة...")
            print(f"📁 اسم الملف المرفوع: {uploaded_file.name}")
            print(f"📊 حجم الملف المرفوع: {uploaded_file.size} بايت")

            # حفظ الملف في مجلد النسخ الاحتياطية مباشرة
            backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
            os.makedirs(backup_dir, exist_ok=True)

            # إنشاء اسم ملف فريد
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f"uploaded_{timestamp}_{uploaded_file.name}"
            file_path = os.path.join(backup_dir, file_name)

            print(f"💾 حفظ الملف في: {file_path}")

            # حفظ الملف
            with open(file_path, 'wb') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            actual_size = os.path.getsize(file_path)
            print(f"✅ تم حفظ الملف بنجاح - الحجم الفعلي: {actual_size} بايت")

            # استعادة مباشرة
            from django.core.management import call_command

            if clear_data:
                print("⚠️ تم تجاهل خيار حذف البيانات القديمة لتجنب مشاكل قاعدة البيانات")

            # استعادة مبسطة جداً
            print(f"🔄 بدء استعادة الملف: {file_path}")            # التحقق من نوع الملف (مع دعم الأحرف الكبيرة والصغيرة)
            if uploaded_file.name.lower().endswith('.gz'):
                print("📦 ملف مضغوط - فك الضغط...")
                import gzip
                import tempfile

                with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as temp_file:
                    temp_path = temp_file.name

                    try:
                        print(f"🔓 فك ضغط من: {file_path}")
                        with gzip.open(file_path, 'rt', encoding='utf-8') as gz_file:
                            content = gz_file.read()

                        print(f"📝 كتابة المحتوى المفكوك إلى: {temp_path}")
                        
                        with open(temp_path, 'w', encoding='utf-8') as json_file:
                            json_file.write(content)

                        temp_size = os.path.getsize(temp_path)
                        print(f"✅ تم فك الضغط بنجاح - حجم الملف المفكوك: {temp_size} بايت")
                          # استعادة من الملف المفكوك
                        print("🔄 استعادة البيانات من الملف المفكوك...")
                        result = _restore_json_simple(temp_path, clear_existing=clear_data)

                    except Exception as gz_error:
                        print(f"❌ خطأ في فك الضغط: {str(gz_error)}")
                        raise
                    finally:
                        # حذف الملف المؤقت مع معالجة أخطاء Windows
                        if os.path.exists(temp_path):
                            try:
                                import time
                                time.sleep(0.1)  # تأخير صغير للسماح لـ Windows بإغلاق الملف
                                os.unlink(temp_path)
                                print(f"🗑️ تم حذف الملف المؤقت: {temp_path}")
                            except PermissionError:
                                print(f"⚠️ لا يمكن حذف الملف المؤقت فوراً (مستخدم من عملية أخرى): {temp_path}")
                                print("💡 سيتم حذفه تلقائياً عند إعادة تشغيل النظام")
                            except Exception as cleanup_error:
                                print(f"⚠️ خطأ في حذف الملف المؤقت: {str(cleanup_error)}")
            else:
                print("📄 ملف JSON عادي - استعادة مباشرة...")
                result = _restore_json_simple(file_path, clear_existing=clear_data)

            # إنشاء رسالة تفصيلية بناءً على النتيجة
            if result:
                success_count = result.get('success_count', 0)
                error_count = result.get('error_count', 0)
                total_count = result.get('total_count', 0)
                
                if error_count == 0:
                    success_message = f"🎉 تم استعادة جميع البيانات بنجاح!\n\n📊 الإحصائيات:\n• إجمالي العناصر: {total_count}\n• تم الاستعادة: {success_count}\n• نسبة النجاح: 100%\n\n✨ تم إصلاح جميع المشاكل تلقائياً!"
                else:
                    success_rate = (success_count / total_count * 100) if total_count > 0 else 0
                    success_message = f"✅ تمت الاستعادة بنجاح!\n\n📊 الإحصائيات:\n• إجمالي العناصر: {total_count}\n• تم الاستعادة: {success_count}\n• فشل: {error_count}\n• نسبة النجاح: {success_rate:.1f}%"
                    
                    if error_count > 0:
                        success_message += f"\n\n⚠️ تحذير: {error_count} عنصر لم يتم استعادته (عادة بسبب بيانات غير متوافقة مع النسخة الحالية)."
                
                messages.success(request, success_message)
            else:
                messages.success(request, _('تم استعادة النسخة الاحتياطية بنجاح.'))

            print("🎉 تمت الاستعادة بنجاح!")

            messages.success(request, _('تم استعادة النسخة الاحتياطية بنجاح.'))
            return redirect('odoo_db_manager:database_detail', pk=database_id)
        except Exception as e:
            error_message = str(e)
            print(f"خطأ في الاستعادة: {error_message}")

            # رسالة خطأ مبسطة
            if "flush" in error_message:
                error_message = "مشكلة في إعدادات قاعدة البيانات. تم تجاهل حذف البيانات القديمة."
            elif "JSON" in error_message or "fixture" in error_message:
                error_message = "مشكلة في تنسيق الملف. تأكد من أن الملف بتنسيق JSON صالح."
            elif "فشل تثبيت البيانات من الملف المضغوط" in error_message:
                error_message = "مشكلة في الملف المضغوط. جرب ملف JSON غير مضغوط."
            else:
                error_message = f"خطأ في الاستعادة: {error_message[:200]}..."

            messages.error(request, _(f'حدث خطأ أثناء استعادة النسخة الاحتياطية: {error_message}'))
            return redirect('odoo_db_manager:backup_upload')

    # الحصول على قواعد البيانات
    databases = Database.objects.all()

    context = {
        'database': database,
        'databases': databases,
        'backup_types': Backup.BACKUP_TYPES,
        'title': _('استعادة من ملف'),
    }

    return render(request, 'odoo_db_manager/backup_upload.html', context)


@login_required
@user_passes_test(is_staff_or_superuser)
def schedule_list(request):
    """عرض قائمة جدولة النسخ الاحتياطية"""
    # الحصول على جدولات النسخ الاحتياطية
    schedules = BackupSchedule.objects.all().order_by('-is_active', '-created_at')

    context = {
        'schedules': schedules,
        'title': _('جدولة النسخ الاحتياطية'),
    }

    return render(request, 'odoo_db_manager/schedule_list.html', context)


@login_required
@user_passes_test(is_staff_or_superuser)
def schedule_detail(request, pk):
    """عرض تفاصيل جدولة النسخة الاحتياطية"""
    # الحصول على جدولة النسخة الاحتياطية
    schedule = get_object_or_404(BackupSchedule, pk=pk)

    # الحصول على النسخ الاحتياطية المرتبطة بهذه الجدولة
    backups = Backup.objects.filter(
        database=schedule.database,
        backup_type=schedule.backup_type,
        is_scheduled=True
    ).order_by('-created_at')

    context = {
        'schedule': schedule,
        'backups': backups,
        'title': _('تفاصيل جدولة النسخة الاحتياطية'),
    }

    return render(request, 'odoo_db_manager/schedule_detail.html', context)


@login_required
@user_passes_test(is_staff_or_superuser)
def schedule_create(request, database_id=None):
    """إنشاء جدولة نسخة احتياطية جديدة"""
    # الحصول على قاعدة البيانات
    database = None
    if database_id:
        database = get_object_or_404(Database, pk=database_id)

    if request.method == 'POST':
        form = BackupScheduleForm(request.POST)
        if form.is_valid():
            # إنشاء جدولة النسخة الاحتياطية
            schedule = form.save(commit=False)
            schedule.created_by = request.user
            schedule.save()

            # حساب موعد التشغيل القادم
            schedule.calculate_next_run()

            # إضافة الجدولة إلى المجدول
            scheduled_backup_service.start()
            scheduled_backup_service._schedule_backup(schedule)

            messages.success(request, _('تم إنشاء جدولة النسخة الاحتياطية بنجاح.'))
            return redirect('odoo_db_manager:schedule_detail', pk=schedule.pk)
    else:
        initial_data = {}
        if database:
            initial_data['database'] = database.id
        form = BackupScheduleForm(initial=initial_data)

    context = {
        'form': form,
        'database': database,
        'title': _('إنشاء جدولة نسخة احتياطية جديدة'),
    }

    return render(request, 'odoo_db_manager/schedule_form.html', context)


@login_required
@user_passes_test(is_staff_or_superuser)
def schedule_update(request, pk):
    """تعديل جدولة نسخة احتياطية"""
    # الحصول على جدولة النسخة الاحتياطية
    schedule = get_object_or_404(BackupSchedule, pk=pk)

    if request.method == 'POST':
        form = BackupScheduleForm(request.POST, instance=schedule)
        if form.is_valid():
            # تحديث جدولة النسخة الاحتياطية
            form.save()

            # حساب موعد التشغيل القادم
            schedule.calculate_next_run()

            # تحديث الجدولة في المجدول
            scheduled_backup_service.start()
            scheduled_backup_service._schedule_backup(schedule)

            messages.success(request, _('تم تحديث جدولة النسخة الاحتياطية بنجاح.'))
            return redirect('odoo_db_manager:schedule_detail', pk=schedule.pk)
    else:
        form = BackupScheduleForm(instance=schedule)

    context = {
        'form': form,
        'schedule': schedule,
        'title': _('تعديل جدولة النسخة الاحتياطية'),
    }

    return render(request, 'odoo_db_manager/schedule_form.html', context)


@login_required
@user_passes_test(is_staff_or_superuser)
def schedule_delete(request, pk):
    """حذف جدولة نسخة احتياطية"""
    # الحصول على جدولة النسخة الاحتياطية
    schedule = get_object_or_404(BackupSchedule, pk=pk)

    if request.method == 'POST':
        # التحقق مما إذا كان المستخدم يريد حذف النسخ الاحتياطية المرتبطة
        delete_backups = request.POST.get('delete_backups') == 'on'

        try:
            # حذف النسخ الاحتياطية المرتبطة إذا طلب المستخدم ذلك
            if delete_backups:
                backups = Backup.objects.filter(
                    database=schedule.database,
                    backup_type=schedule.backup_type,
                    is_scheduled=True
                )
                for backup in backups:
                    # حذف ملف النسخة الاحتياطية
                    if os.path.exists(backup.file_path):
                        os.unlink(backup.file_path)
                    # حذف سجل النسخة الاحتياطية
                    backup.delete()

            # حذف الجدولة من المجدول
            job_id = f"backup_{schedule.id}"
            scheduled_backup_service.remove_job(job_id)

            # حذف جدولة النسخة الاحتياطية
            schedule.delete()

            messages.success(request, _('تم حذف جدولة النسخة الاحتياطية بنجاح.'))
            return redirect('odoo_db_manager:schedule_list')
        except Exception as e:
            messages.error(request, _(f'حدث خطأ أثناء حذف جدولة النسخة الاحتياطية: {str(e)}'))
            return redirect('odoo_db_manager:schedule_detail', pk=schedule.pk)

    context = {
        'schedule': schedule,
        'title': _('حذف جدولة النسخة الاحتياطية'),
    }

    return render(request, 'odoo_db_manager/schedule_delete.html', context)


@login_required
@user_passes_test(is_staff_or_superuser)
def schedule_toggle(request, pk):
    """تنشيط/إيقاف جدولة نسخة احتياطية"""
    # الحصول على جدولة النسخة الاحتياطية
    schedule = get_object_or_404(BackupSchedule, pk=pk)

    # تغيير حالة الجدولة
    schedule.is_active = not schedule.is_active
    schedule.save()

    # تحديث الجدولة في المجدول
    if schedule.is_active:
        scheduled_backup_service.start()
        scheduled_backup_service._schedule_backup(schedule)
        messages.success(request, _('تم تنشيط جدولة النسخة الاحتياطية بنجاح.'))
    else:
        job_id = f"backup_{schedule.id}"
        scheduled_backup_service.remove_job(job_id)
        messages.success(request, _('تم إيقاف جدولة النسخة الاحتياطية بنجاح.'))

    return redirect('odoo_db_manager:schedule_detail', pk=schedule.pk)


@login_required
@user_passes_test(is_staff_or_superuser)
def schedule_run_now(request, pk):
    """تشغيل جدولة نسخة احتياطية الآن"""
    # الحصول على جدولة النسخة الاحتياطية
    schedule = get_object_or_404(BackupSchedule, pk=pk)

    try:
        # تشغيل الجدولة الآن
        backup = scheduled_backup_service.run_job_now(schedule.id)
        if backup:
            messages.success(request, _('تم إنشاء النسخة الاحتياطية بنجاح.'))
        else:
            messages.error(request, _('فشل إنشاء النسخة الاحتياطية.'))
    except Exception as e:
        messages.error(request, _(f'حدث خطأ أثناء إنشاء النسخة الاحتياطية: {str(e)}'))

    return redirect('odoo_db_manager:schedule_detail', pk=schedule.pk)


@login_required
@user_passes_test(is_staff_or_superuser)
def scheduler_status(request):
    """عرض حالة المجدول وإصلاح المشاكل"""
    from .services.scheduled_backup_service import scheduled_backup_service, get_scheduler

    context = {
        'title': _('حالة مجدول النسخ الاحتياطية'),
    }

    try:
        # فحص حالة المجدول
        scheduler = get_scheduler()
        context['scheduler_running'] = scheduler.running if scheduler else False
        context['scheduler_available'] = scheduler is not None

        if scheduler:
            context['scheduler_jobs'] = len(scheduler.get_jobs())
        else:
            context['scheduler_jobs'] = 0

        # فحص الجدولات النشطة
        active_schedules = BackupSchedule.objects.filter(is_active=True)
        context['active_schedules_count'] = active_schedules.count()
        context['active_schedules'] = active_schedules

        # فحص النسخ الاحتياطية الأخيرة
        recent_backups = Backup.objects.filter(
            is_scheduled=True
        ).order_by('-created_at')[:5]
        context['recent_scheduled_backups'] = recent_backups

    except Exception as e:
        context['error'] = str(e)
        messages.error(request, f'خطأ في فحص حالة المجدول: {str(e)}')

    # معالجة الطلبات
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'restart_scheduler':
            try:
                scheduled_backup_service.stop()
                scheduled_backup_service.start()
                messages.success(request, 'تم إعادة تشغيل المجدول بنجاح')
            except Exception as e:
                messages.error(request, f'فشل إعادة تشغيل المجدول: {str(e)}')

        elif action == 'run_manual_backup':
            try:
                from django.core.management import call_command
                call_command('run_scheduled_backups', force=True)
                messages.success(request, 'تم تشغيل النسخ الاحتياطية يدوياً')
            except Exception as e:
                messages.error(request, f'فشل تشغيل النسخ الاحتياطية: {str(e)}')

        return redirect('odoo_db_manager:scheduler_status')

    return render(request, 'odoo_db_manager/scheduler_status.html', context)


def _restore_json_simple(file_path, clear_existing=False):
    """استعادة ملف JSON بطريقة محسنة"""
    import json
    from django.core import serializers
    from django.apps import apps
    from django.db import transaction

    try:
        print(f"📖 قراءة ملف JSON: {file_path}")

        # التحقق من نوع الملف أولاً
        if file_path.lower().endswith('.gz'):
            raise ValueError("هذا ملف مضغوط (.gz). يجب فك ضغطه أولاً قبل استدعاء هذه الدالة.")

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)        # التحقق من نوع البيانات مع تحسين التحقق
        if not isinstance(data, list):
            # التحقق من نوع الملف
            if isinstance(data, dict):
                # فحص إضافي للتأكد من أنه ليس service account credentials
                if 'private_key' in data and 'client_email' in data and 'project_id' in data:
                    raise ValueError("هذا الملف يبدو وكأنه ملف Google Service Account Credentials وليس نسخة احتياطية للنظام. يرجى رفع ملف نسخة احتياطية صالح بتنسيق Django fixture.")
                elif 'model' in data and 'fields' in data:
                    # إذا كان dictionary واحد بدلاً من قائمة، اجعله قائمة
                    data = [data]
                # فحص لتنسيقات أخرى قد تكون نسخ احتياطية
                elif 'version' in data or 'created_at' in data or 'database' in data:
                    # قد يكون تنسيق نسخة احتياطية آخر - محاولة التعامل معه
                    print("⚠️ تنسيق نسخة احتياطية غير مألوف - سيتم تجاهل هذا الملف")
                    raise ValueError("تنسيق النسخة الاحتياطية غير مدعوم. يرجى استخدام ملف بتنسيق Django fixture (JSON).")
                else:
                    raise ValueError("تنسيق الملف غير صالح. يجب أن يكون ملف JSON يحتوي على قائمة من البيانات أو بيانات Django fixture.")
            else:
                raise ValueError(f"تنسيق البيانات غير مدعوم: {type(data)}. يجب أن تكون البيانات عبارة عن قائمة أو قاموس.")

        print(f"✅ تم تحميل {len(data)} عنصر من الملف")

        # تحضير ContentTypes المطلوبة قبل بدء الاستعادة
        print("🔧 التحضير لاستعادة شاملة...")
        from django.contrib.contenttypes.models import ContentType
        
        # إنشاء ContentTypes للتطبيقات الأساسية إذا لم تكن موجودة
        required_content_types = [
            ('inventory', 'product'),
            ('inventory', 'category'),
            ('inventory', 'brand'),
            ('inventory', 'warehouse'),
            ('inventory', 'stocktransaction'),
            ('orders', 'order'),
            ('orders', 'orderitem'),
            ('customers', 'customer'),
            ('customers', 'customernote'),
            ('inspections', 'inspection'),
            ('installations', 'installation'),
            ('reports', 'report'),
            ('accounts', 'department'),
            ('accounts', 'branch'),
        ]
        
        for app_label, model_name in required_content_types:
            try:
                ContentType.objects.get_or_create(
                    app_label=app_label,
                    model=model_name
                )
            except Exception:
                # تجاهل الأخطاء في إنشاء ContentTypes
                pass
        
        print("✅ تم التحضير لاستعادة شاملة")        # ترتيب البيانات حسب الأولوية (الجداول التي لا تعتمد على غيرها أولاً)
        priority_order = [
            # ContentTypes أولاً
            'contenttypes.contenttype',
            # المستخدمين والمجموعات
            'auth.user',
            'auth.group',
            # الأقسام والفروع
            'accounts.department',
            'accounts.branch',
            # الصلاحيات (بعد إنشاء ContentTypes)
            'auth.permission',
            # العملاء والفئات
            'customers.customer',
            'inventory.category',
            'inventory.brand',
            # المنتجات والمستودعات
            'inventory.warehouse',
            'inventory.product',
            # الطلبات والفحوصات
            'orders.order',
            'orders.orderitem',
            'inspections.inspection',
            'installations.installation',
            # التقارير والنسخ الاحتياطية
            'reports.report',
            'odoo_db_manager.database',
            'odoo_db_manager.backup',
            'odoo_db_manager.backupschedule',
            'odoo_db_manager.importlog',
            # المعاملات والملاحظات (في النهاية)
            'inventory.stocktransaction',
            'customers.customernote',
        ]

        # ترتيب البيانات
        sorted_data = []
        remaining_data = []

        for model_name in priority_order:
            for item in data:
                if item.get('model') == model_name:
                    sorted_data.append(item)

        # إضافة باقي البيانات
        for item in data:
            if item not in sorted_data:
                remaining_data.append(item)

        final_data = sorted_data + remaining_data

        # تطهير البيانات مسبقاً لإصلاح المشاكل المعروفة
        print("🔧 تطهير البيانات المسبق...")
        for item in final_data:
            model_name = item.get('model', 'unknown')
            fields = item.get('fields', {})
            
            # معالجة خاصة لـ SystemSettings
            if model_name == 'accounts.systemsettings':
                # تحويل default_currency إلى currency
                if 'default_currency' in fields:
                    default_curr = fields.pop('default_currency', 'SAR')
                    fields['currency'] = default_curr
                    print(f"🔄 تم تحويل default_currency إلى currency مسبقاً: {default_curr}")
                
                # إزالة خصائص قديمة أخرى
                old_fields = ['timezone', 'date_format', 'time_format']
                for field in old_fields:
                    if field in fields:
                        removed_value = fields.pop(field, None)
                        print(f"🗑️ تم إزالة الخاصية القديمة {field}: {removed_value}")
                
                item['fields'] = fields

        # حذف البيانات القديمة إذا تم طلب ذلك
        if clear_existing:
            print("🗑️ حذف البيانات القديمة...")
            models_to_clear = set()
            for item in final_data:
                model_name = item.get('model')
                if model_name:
                    models_to_clear.add(model_name)

            # حذف البيانات بترتيب عكسي
            for model_name in reversed(priority_order):
                if model_name in models_to_clear:
                    try:
                        app_label, model_class = model_name.split('.')
                        model = apps.get_model(app_label, model_class)
                        count = model.objects.count()
                        if count > 0:
                            model.objects.all().delete()
                            print(f"🗑️ تم حذف {count} سجل من {model_name}")
                    except Exception as e:
                        print(f"⚠️ خطأ في حذف {model_name}: {str(e)}")

        # استعادة البيانات مع معالجة محسنة للأخطاء
        success_count = 0
        error_count = 0
        failed_items = []

        print("🔄 بدء استعادة العناصر...")

        # محاولة أولى
        for i, item in enumerate(final_data):
            try:
                with transaction.atomic():
                    for obj in serializers.deserialize('json', json.dumps([item])):
                        obj.save()
                success_count += 1

                # طباعة تقدم كل 50 عنصر
                if (i + 1) % 50 == 0:
                    print(f"📊 تم معالجة {i + 1} عنصر...")

            except Exception as item_error:
                error_count += 1
                failed_items.append((i, item, str(item_error)))
                # طباعة تفاصيل الخطأ للعناصر القليلة الأولى فقط
                if error_count <= 5:
                    print(f"⚠️ خطأ في العنصر {i + 1} ({item.get('model', 'unknown')}): {str(item_error)[:100]}...")        # محاولة ثانية للعناصر الفاشلة (قد تكون فشلت بسبب ترتيب الاعتمادات)
        if failed_items:
            print(f"🔄 محاولة ثانية لـ {len(failed_items)} عنصر فاشل...")
            second_attempt_success = 0
            
            for original_index, item, original_error in failed_items:
                try:
                    with transaction.atomic():                        # معالجة أخطاء محددة قبل المحاولة الثانية
                        item_copy = item.copy()
                        fields = item_copy.get('fields', {})
                        model_name = item_copy.get('model', 'unknown')
                        
                        # معالجة مشاكل ContentType (الصلاحيات المفقودة)
                        if 'ContentType matching query does not exist' in original_error:
                            print(f"🔧 إصلاح مشكلة ContentType: {model_name}")
                            # تجاهل هذا العنصر مؤقتاً وإنشاؤه لاحقاً
                            continue
                        
                        # معالجة مشاكل الصلاحيات
                        elif 'permission_id' in original_error and 'foreign key' in original_error:
                            print(f"🔧 إصلاح مشكلة الصلاحيات: {model_name}")
                            fields.pop('user_permissions', None)
                            fields.pop('groups', None)
                            item_copy['fields'] = fields
                          # معالجة مشاكل الخصائص المفقودة
                        elif 'has no attribute' in original_error:
                            print(f"🔧 إصلاح مشكلة خاصية مفقودة: {model_name}")
                            
                            # معالجة خاصة لـ SystemSettings
                            if model_name == 'accounts.systemsettings':
                                # إزالة الخصائص القديمة وإضافة تعيين صحيح
                                if 'default_currency' in original_error:
                                    # إزالة default_currency وتعيين currency بدلاً منه
                                    default_curr = fields.pop('default_currency', 'SAR')
                                    if 'currency' not in fields:
                                        fields['currency'] = default_curr
                                    print(f"🔄 تم تحويل default_currency إلى currency: {default_curr}")
                                
                                # إزالة خصائص أخرى مفقودة
                                problematic_fields = ['timezone', 'date_format', 'time_format']
                                for field in problematic_fields:
                                    if field in fields:
                                        removed_value = fields.pop(field, None)
                                        print(f"🗑️ تم إزالة الخاصية المفقودة {field}: {removed_value}")
                            else:
                                # معالجة عامة للموديلات الأخرى
                                problematic_fields = ['default_currency', 'timezone', 'date_format', 'time_format']
                                for field in problematic_fields:
                                    if field in original_error and field in fields:
                                        removed_value = fields.pop(field, None)
                                        print(f"🗑️ تم إزالة الخاصية المفقودة {field}: {removed_value}")
                            
                            item_copy['fields'] = fields
                        
                        # معالجة مشاكل المفاتيح الخارجية
                        elif 'foreign key constraint' in original_error or 'violates foreign key constraint' in original_error:
                            print(f"🔧 محاولة إصلاح مفتاح خارجي مفقود: {model_name}")
                            # إزالة المفاتيح الخارجية المشكوك فيها
                            foreign_key_fields = ['customer', 'user', 'order', 'product', 'category']
                            for field in foreign_key_fields:
                                if field in fields and fields[field] is None:
                                    fields.pop(field, None)
                            item_copy['fields'] = fields
                        
                        # معالجة مشاكل القيود الفريدة
                        elif 'UNIQUE constraint failed' in original_error or 'duplicate key value' in original_error:
                            print(f"🔧 إصلاح مشكلة التكرار: {model_name}")
                            # تجاهل هذا العنصر إذا كان مكرراً
                            continue
                        
                        for obj in serializers.deserialize('json', json.dumps([item_copy])):
                            obj.save()
                    second_attempt_success += 1
                    success_count += 1
                    error_count -= 1
                    print(f"✅ نجح إصلاح العنصر {original_index + 1}")
                except Exception as e:
                    # طباعة تفاصيل الأخطاء المستمرة
                    if len(failed_items) - second_attempt_success <= 10:
                        print(f"❌ فشل نهائي في العنصر {original_index + 1} ({item.get('model', 'unknown')}): {str(e)[:200]}...")

            print(f"✅ نجحت المحاولة الثانية في استعادة {second_attempt_success} عنصر إضافي")

        # محاولة ثالثة: إصلاح مشاكل ContentType المتبقية
        remaining_failed = [item for item in failed_items if 'ContentType matching query does not exist' in item[2]]
        if remaining_failed:
            print(f"🔄 محاولة ثالثة لإصلاح {len(remaining_failed)} عنصر بمشاكل ContentType...")
            
            # إنشاء ContentTypes المفقودة أولاً
            from django.contrib.contenttypes.models import ContentType
            
            third_attempt_success = 0
            for original_index, item, original_error in remaining_failed:
                try:
                    with transaction.atomic():
                        model_name = item.get('model', 'unknown')
                        
                        # محاولة إنشاء ContentType المفقود
                        if model_name == 'auth.permission':
                            fields = item.get('fields', {})
                            content_type_info = fields.get('content_type', [])
                            
                            if content_type_info and len(content_type_info) >= 2:
                                app_label = content_type_info[0]
                                model_class = content_type_info[1]
                                
                                # محاولة إنشاء أو العثور على ContentType
                                try:
                                    content_type, created = ContentType.objects.get_or_create(
                                        app_label=app_label,
                                        model=model_class
                                    )
                                    if created:
                                        print(f"🆕 تم إنشاء ContentType مفقود: {app_label}.{model_class}")
                                except Exception as ct_error:
                                    print(f"⚠️ لا يمكن إنشاء ContentType: {app_label}.{model_class} - {str(ct_error)[:100]}")
                                    continue
                        
                        # الآن محاولة استعادة العنصر مرة أخرى
                        for obj in serializers.deserialize('json', json.dumps([item])):
                            obj.save()
                        
                        third_attempt_success += 1
                        success_count += 1
                        error_count -= 1
                        print(f"✅ نجح إصلاح ContentType للعنصر {original_index + 1}")
                        
                except Exception as e:
                    # تجاهل الأخطاء في المحاولة الثالثة
                    pass
            
            if third_attempt_success > 0:
                print(f"✅ نجحت المحاولة الثالثة في استعادة {third_attempt_success} عنصر إضافي")

        print(f"🎯 تمت الاستعادة: {success_count} عنصر بنجاح، {error_count} عنصر فشل نهائياً")
        
        if error_count > 0:
            print(f"⚠️ تحذير: {error_count} عنصر لم يتم استعادته. قد تحتاج لمراجعة البيانات.")

        return {
            'success_count': success_count,
            'error_count': error_count,
            'total_count': len(final_data)
        }

    except ValueError as ve:
        # خطأ في تنسيق الملف
        print(f"❌ خطأ في تنسيق الملف: {str(ve)}")
        raise ve
    except Exception as e:
        print(f"❌ خطأ في قراءة الملف: {str(e)}")
        raise Exception(f"فشل في قراءة أو معالجة الملف: {str(e)}")


# ==================== عروض Google Drive ====================

@login_required
@user_passes_test(is_staff_or_superuser)
def google_drive_settings(request):
    """إدارة إعدادات Google Drive"""
    # الحصول على الإعدادات الحالية أو إنشاء جديدة
    config = GoogleDriveConfig.get_active_config()

    if request.method == 'POST':
        form = GoogleDriveConfigForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            config = form.save(commit=False)
            config.created_by = request.user
            config.save()

            messages.success(request, _('تم حفظ إعدادات Google Drive بنجاح.'))
            return redirect('odoo_db_manager:google_drive_settings')
        else:
            messages.error(request, _('يرجى تصحيح الأخطاء في النموذج.'))
    else:
        form = GoogleDriveConfigForm(instance=config)

    context = {
        'form': form,
        'config': config,
        'title': _('إعدادات Google Drive'),
    }

    return render(request, 'odoo_db_manager/google_drive_settings.html', context)


@login_required
@user_passes_test(is_staff_or_superuser)
def google_drive_test_connection(request):
    """اختبار الاتصال مع Google Drive"""
    if request.method == 'POST':
        try:
            from inspections.services.google_drive_service import get_google_drive_service

            # الحصول على خدمة Google Drive
            drive_service = get_google_drive_service()

            if not drive_service:
                return JsonResponse({
                    'success': False,
                    'message': 'فشل في تهيئة خدمة Google Drive'
                })

            # اختبار الاتصال
            result = drive_service.test_connection()

            if result['success']:
                messages.success(request, result['message'])
            else:
                messages.error(request, result['message'])

            return JsonResponse(result)

        except Exception as e:
            error_message = f'خطأ في اختبار الاتصال: {str(e)}'
            messages.error(request, error_message)
            return JsonResponse({
                'success': False,
                'message': error_message
            })

    return JsonResponse({
        'success': False,
        'message': 'طريقة الطلب غير صحيحة'
    })


@login_required
@user_passes_test(is_staff_or_superuser)
def google_drive_create_test_folder(request):
    """إنشاء مجلد تجريبي في Google Drive"""
    if request.method == 'POST':
        try:
            from inspections.services.google_drive_service import create_test_folder

            # إنشاء مجلد تجريبي
            result = create_test_folder()

            if result:
                messages.success(request, f'تم إنشاء مجلد تجريبي بنجاح: {result["name"]}')
                return JsonResponse({
                    'success': True,
                    'message': f'تم إنشاء مجلد تجريبي بنجاح',
                    'folder': result
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'فشل في إنشاء المجلد التجريبي'
                })

        except Exception as e:
            error_message = f'خطأ في إنشاء المجلد التجريبي: {str(e)}'
            messages.error(request, error_message)
            return JsonResponse({
                'success': False,
                'message': error_message
            })

    return JsonResponse({
        'success': False,
        'message': 'طريقة الطلب غير صحيحة'
    })


@login_required
@user_passes_test(is_staff_or_superuser)
def google_drive_test_file_upload(request):
    """اختبار رفع ملف تجريبي إلى المجلد المحدد"""
    if request.method == 'POST':
        try:
            from inspections.services.google_drive_service import test_file_upload_to_folder

            # اختبار رفع ملف
            result = test_file_upload_to_folder()

            if result and result.get('success'):
                messages.success(request, 'تم اختبار رفع الملف بنجاح')
                return JsonResponse({
                    'success': True,
                    'message': result.get('message'),
                    'details': {
                        'file_name': result.get('file_name'),
                        'folder_id': result.get('folder_id')
                    }
                })
            else:
                error_message = result.get('message') if result else 'فشل في اختبار رفع الملف'
                return JsonResponse({
                    'success': False,
                    'message': error_message
                })

        except Exception as e:
            error_message = f'خطأ في اختبار رفع الملف: {str(e)}'
            messages.error(request, error_message)
            return JsonResponse({
                'success': False,
                'message': error_message
            })

    return JsonResponse({
        'success': False,
        'message': 'طريقة الطلب غير صحيحة'
    })

@login_required
@user_passes_test(is_staff_or_superuser)
def database_register(request):
    """تسجيل قاعدة بيانات مكتشفة في النظام"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            db_name = data.get('name')
            
            if not db_name:
                return JsonResponse({'success': False, 'message': 'اسم قاعدة البيانات مطلوب'})
            
            # التحقق من عدم وجود قاعدة البيانات مسبقاً
            if Database.objects.filter(name=db_name).exists():
                return JsonResponse({'success': False, 'message': 'قاعدة البيانات مسجلة بالفعل'})
            
            # الحصول على معلومات الاتصال الافتراضية من Django settings
            from django.conf import settings
            default_db = settings.DATABASES['default']
            
            # إنشاء معلومات الاتصال
            connection_info = {
                'ENGINE': 'django.db.backends.postgresql',
                'HOST': default_db.get('HOST', 'localhost'),
                'PORT': default_db.get('PORT', '5432'),
                'USER': default_db.get('USER', 'postgres'),
                'PASSWORD': default_db.get('PASSWORD', ''),
                'NAME': db_name,
            }
            
            # إنشاء سجل قاعدة البيانات
            database = Database.objects.create(
                name=db_name,
                db_type='postgresql',
                connection_info=connection_info,
                status=True,  # نفترض أنها متاحة لأنها مكتشفة
            )
            
            return JsonResponse({
                'success': True, 
                'message': f'تم تسجيل قاعدة البيانات "{db_name}" بنجاح',
                'database_id': database.id
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'حدث خطأ: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'})

@login_required
@user_passes_test(is_staff_or_superuser)
def database_refresh_status(request):
    """تحديث حالة الاتصال لجميع قواعد البيانات"""
    if request.method == 'POST':
        try:
            database_service = DatabaseService()
            databases = Database.objects.all()
            updated_count = 0
            
            for db in databases:
                try:
                    success, message = database_service.test_connection(db.connection_info)
                    if db.status != success:
                        db.status = success
                        db.error_message = message if not success else ""
                        db.save()
                        updated_count += 1
                except Exception as e:
                    if db.status != False:
                        db.status = False
                        db.error_message = str(e)
                        db.save()
                        updated_count += 1
            
            return JsonResponse({
                'success': True,
                'message': f'تم تحديث حالة {updated_count} قاعدة بيانات',
                'updated_count': updated_count
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'حدث خطأ: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'طريقة غير مسموحة'})


def _create_default_user(database):
    """إنشاء مستخدم افتراضي في قاعدة البيانات الجديدة"""
    try:
        import psycopg2
        from django.contrib.auth.hashers import make_password
        
        # الاتصال بقاعدة البيانات الجديدة
        conn = psycopg2.connect(
            dbname=database.connection_info.get('NAME'),
            user=database.connection_info.get('USER'),
            password=database.connection_info.get('PASSWORD'),
            host=database.connection_info.get('HOST', 'localhost'),
            port=database.connection_info.get('PORT', '5432')
        )
        conn.autocommit = True
        cursor = conn.cursor()
          # التحقق من وجود جدول المستخدمين
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'accounts_user'
            );
        """)
        
        table_exists = cursor.fetchone()
        if not table_exists or not table_exists[0]:
            print("جدول المستخدمين غير موجود في قاعدة البيانات الجديدة")
            cursor.close()
            conn.close()
            return False
        
        # التحقق من عدد الأعمدة في الجدول للتأكد من اكتمال الـ migrations
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'accounts_user'
        """)
        
        column_count = cursor.fetchone()
        if not column_count or column_count[0] < 10:  # نتوقع على الأقل 10 أعمدة
            print("جدول المستخدمين غير مكتمل، migrations لم تطبق بالكامل")
            cursor.close()
            conn.close()
            return False
        
        # التحقق من عدم وجود مستخدم admin مسبقاً
        cursor.execute("SELECT COUNT(*) FROM accounts_user WHERE username = %s", ('admin',))
        admin_result = cursor.fetchone()
        admin_exists = admin_result and admin_result[0] > 0
        
        if admin_exists:
            print("المستخدم admin موجود بالفعل")
            cursor.close()
            conn.close()
            return False
        
        # إنشاء كلمة مرور مُشفرة
        hashed_password = make_password('admin123')
          # إدراج المستخدم الجديد
        cursor.execute("""
            INSERT INTO accounts_user (
                username, password, email, first_name, last_name,
                is_staff, is_active, is_superuser, date_joined
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, ('admin', hashed_password, 'admin@example.com', 'مدير', 'النظام', 
              True, True, True, timezone.now()))        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("تم إنشاء المستخدم admin بنجاح")
        return True
        
    except Exception as e:
        print(f"خطأ في إنشاء المستخدم admin: {str(e)}")
        return False


def _apply_migrations_to_database(database):
    try:
        import subprocess
        import os
        from django.conf import settings
        
        # إنشاء DATABASE_URL للقاعة الجديدة
        conn_info = database.connection_info
        database_url = f"postgres://{conn_info.get('USER')}:{conn_info.get('PASSWORD')}@{conn_info.get('HOST', 'localhost')}:{conn_info.get('PORT', '5432')}/{conn_info.get('NAME')}"
        
        # تطبيق migrations في قاعدة البيانات الجديدة
        env = os.environ.copy()
        env['DATABASE_URL'] = database_url
          # تشغيل migrate command مع تجاهل أخطاء django_apscheduler
        migrate_cmd = [
            'python', 'manage.py', 'migrate', '--fake-initial'
        ]
        
        result = subprocess.run(
            migrate_cmd,
            env=env,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            cwd=settings.BASE_DIR        )
        
        if result.returncode == 0:
            print(f"تم تطبيق migrations في قاعدة البيانات {database.name} بنجاح")
            return True
        else:
            error_msg = result.stderr if result.stderr else result.stdout
            print(f"فشل في تطبيق migrations: {error_msg}")
            # التحقق إذا كان الخطأ متعلق بـ django_apscheduler فقط
            if 'django_apscheduler' in error_msg and 'column' in error_msg and 'does not exist' in error_msg:
                print("خطأ django_apscheduler - سيتم تجاهله")
                return True  # نعتبر العملية ناجحة رغم خطأ django_apscheduler
            return False
            
    except Exception as e:
        print(f"خطأ في تطبيق migrations: {str(e)}")
        return False