"""
خدمة إدارة قواعد البيانات
"""

import os
import subprocess
import json
import sqlite3
import re
from django.conf import settings
from ..models import Database

class DatabaseService:
    """خدمة إدارة قواعد البيانات"""
    
    def activate_database(self, database_id):
        """تنشيط قاعدة بيانات باستخدام طريقة النموذج الجديدة"""
        try:
            # الحصول على قاعدة البيانات
            database = Database.objects.get(id=database_id)
            
            # التحقق من جداول Django
            tables_status = self.check_django_tables(database)
            
            # إذا كانت هناك حاجة للترحيلات
            if tables_status.get('needs_migrations'):
                migration_result = self.run_migrations(database)
                if not migration_result['success']:
                    print("تحذير: فشل تشغيل الترحيلات. قد تظهر أخطاء عند تسجيل الدخول.")
                    print(f"الخطأ: {migration_result.get('error', 'خطأ غير معروف')}")
            
            # تنشيط قاعدة البيانات
            return database.activate()
            
        except Exception as e:
            print(f"حدث خطأ أثناء تنشيط قاعدة البيانات: {str(e)}")
            raise

    def create_database(self, name, db_type, connection_info, force_create=False):
        """إنشاء قاعدة بيانات جديدة"""
        # التحقق من وجود قاعدة البيانات في النظام (وليس في PostgreSQL)
        if not force_create and Database.objects.filter(name=name).exists():
            raise ValueError(f"قاعدة البيانات '{name}' موجودة بالفعل في النظام")

        # تأكد من أن اسم قاعدة البيانات موجود في connection_info
        if db_type == 'postgresql':
            # إذا لم يتم تحديد اسم قاعدة البيانات، استخدم الاسم المدخل
            if 'NAME' not in connection_info or not connection_info['NAME']:
                connection_info['NAME'] = name

            # طباعة معلومات تشخيصية
            print(f"إنشاء قاعدة بيانات PostgreSQL: {name}")
            print(f"اسم قاعدة البيانات في PostgreSQL: {connection_info['NAME']}")
        elif db_type == 'sqlite3':
            # إذا لم يتم تحديد اسم ملف SQLite، استخدم الاسم المدخل
            if 'NAME' not in connection_info or not connection_info['NAME']:
                connection_info['NAME'] = f"{name}.sqlite3"

            # طباعة معلومات تشخيصية
            print(f"إنشاء قاعدة بيانات SQLite: {name}")
            print(f"مسار ملف SQLite: {connection_info['NAME']}")

        try:
            # إنشاء قاعدة البيانات حسب النوع
            if db_type == 'postgresql':
                # الحصول على اسم قاعدة البيانات في PostgreSQL
                pg_db_name = connection_info['NAME']

                # التحقق من وجود قاعدة البيانات في PostgreSQL إذا كان ذلك ممكنًا
                if not force_create and self._check_postgresql_db_exists(
                    name=pg_db_name,
                    user=connection_info.get('USER', ''),
                    password=connection_info.get('PASSWORD', ''),
                    host=connection_info.get('HOST', 'localhost'),
                    port=connection_info.get('PORT', '5432')
                ):
                    raise ValueError(f"قاعدة البيانات '{pg_db_name}' موجودة بالفعل في PostgreSQL")

                # إنشاء قاعدة البيانات PostgreSQL
                self._create_postgresql_database(
                    name=pg_db_name,
                    user=connection_info.get('USER', ''),
                    password=connection_info.get('PASSWORD', ''),
                    host=connection_info.get('HOST', 'localhost'),
                    port=connection_info.get('PORT', '5432')
                )
            elif db_type == 'sqlite3':
                # إنشاء قاعدة بيانات SQLite
                self._create_sqlite_database(
                    name=connection_info['NAME']
                )
        except Exception as e:
            # تسجيل الخطأ ولكن الاستمرار في إنشاء السجل
            print(f"تحذير: {str(e)}")
            # تحديث معلومات الاتصال لتشير إلى أن قاعدة البيانات لم يتم إنشاؤها فعلياً
            connection_info['_CREATED'] = False
            connection_info['_ERROR'] = str(e)
        else:
            # تحديث معلومات الاتصال لتشير إلى أن قاعدة البيانات تم إنشاؤها بنجاح
            connection_info['_CREATED'] = True

        # إنشاء سجل قاعدة البيانات
        database = Database.objects.create(
            name=name,
            db_type=db_type,
            connection_info=connection_info
        )

        return database

    def _check_postgresql_db_exists(self, name, user, password, host, port):
        """التحقق من وجود قاعدة بيانات PostgreSQL"""
        # التحقق من وجود أداة psql
        if not self._check_command_exists('psql'):
            # إذا لم تكن أداة psql موجودة، نفترض أن قاعدة البيانات غير موجودة
            return False

        # التحقق من صحة اسم قاعدة البيانات
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)

        # التحقق من وجود قاعدة البيانات باستخدام psql
        env = os.environ.copy()
        env['PGPASSWORD'] = password

        # استعلام للتحقق من وجود قاعدة البيانات
        check_cmd = [
            'psql',
            '-h', host,
            '-p', port,
            '-U', user,
            '-lqt'  # قائمة قواعد البيانات بتنسيق جدولي بدون عنوان
        ]

        try:
            result = subprocess.run(check_cmd, env=env, check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True)

            # البحث عن قاعدة البيانات في النتيجة
            for line in result.stdout.splitlines():
                if line.strip().startswith(safe_name + '|'):
                    return True

            return False
        except Exception:
            # في حالة حدوث خطأ، نفترض أن قاعدة البيانات غير موجودة
            return False

    def _create_sqlite_database(self, name):
        """إنشاء قاعدة بيانات SQLite"""
        # التأكد من أن المسار موجود
        db_path = os.path.join(settings.BASE_DIR, name)
        db_dir = os.path.dirname(db_path)

        # إنشاء المجلد إذا لم يكن موجوداً
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # إنشاء قاعدة بيانات SQLite فارغة
        conn = sqlite3.connect(db_path)
        conn.close()

        return True

    def _create_postgresql_database(self, name, user, password, host, port):
        """إنشاء قاعدة بيانات PostgreSQL"""
        # التحقق من وجود أداة psql
        if not self._check_command_exists('psql'):
            raise RuntimeError("أداة psql غير موجودة. يرجى التأكد من تثبيت PostgreSQL وإضافته إلى مسار النظام.")

        # التحقق من صحة اسم قاعدة البيانات
        # استبدال الأحرف غير المسموح بها بالشرطة السفلية
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)

        # إنشاء قاعدة البيانات باستخدام psql
        env = os.environ.copy()
        env['PGPASSWORD'] = password

        # إنشاء قاعدة البيانات
        create_cmd = [
            'psql',
            '-h', host,
            '-p', port,
            '-U', user,
            '-c', f"CREATE DATABASE \"{safe_name}\";"
        ]

        try:
            subprocess.run(create_cmd, env=env, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"فشل إنشاء قاعدة البيانات: {e.stderr.decode()}")
        except FileNotFoundError:
            raise RuntimeError("أداة psql غير موجودة. يرجى التأكد من تثبيت PostgreSQL وإضافته إلى مسار النظام.")

    def _check_command_exists(self, command):
        """التحقق من وجود أمر في النظام"""
        try:
            # استخدام 'where' في Windows أو 'which' في Unix
            if os.name == 'nt':  # Windows
                check_cmd = ['where', command]
            else:  # Unix/Linux/Mac
                check_cmd = ['which', command]

            result = subprocess.run(check_cmd,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
            return result.returncode == 0
        except:
            return False

    def activate_database(self, database_id):
        """تنشيط قاعدة بيانات"""
        # إلغاء تنشيط جميع قواعد databases
        Database.objects.all().update(is_active=False)

        # تنشيط قاعدة البيانات المحددة
        database = Database.objects.get(id=database_id)
        database.is_active = True
        database.save()

        # تحديث ملف الإعدادات
        self._update_settings_file(database)

        return database

    def _update_settings_file(self, database):
        """تحديث ملف إعدادات قاعدة البيانات"""
        import json as _json  # استخدام اسم مختلف محليًا لتجنب أي تعارض
        # إنشاء إعدادات قاعدة البيانات
        if database:
            connection_info = database.connection_info
            if isinstance(connection_info, str):
                try:
                    connection_info = _json.loads(connection_info)
                except Exception:
                    connection_info = {}
            elif connection_info is None:
                connection_info = {}
            db_settings = {
                'active_db': database.id,
                'databases': {
                    str(database.id): {
                        'ENGINE': f"django.db.backends.{database.db_type}",
                        **connection_info
                    }
                }
            }
        else:
            db_settings = {
                'active_db': None,
                'databases': {}
            }
        settings_file = os.path.join(settings.BASE_DIR, 'db_settings.json')
        with open(settings_file, 'w') as f:
            _json.dump(db_settings, f, indent=4)

    def discover_postgresql_databases(self):
        """اكتشاف قواعد البيانات الموجودة في PostgreSQL"""
        try:
            # الحصول على معلومات الاتصال من إعدادات Django
            from django.conf import settings
            db_settings = settings.DATABASES['default']
            
            user = db_settings.get('USER', 'admin')
            password = db_settings.get('PASSWORD', 'admin123')
            host = db_settings.get('HOST', 'localhost')
            port = str(db_settings.get('PORT', '5433'))
            
            # استخدام psycopg2 للاتصال بقاعدة البيانات
            import psycopg2
            
            # إنشاء اتصال بقاعدة البيانات postgres الافتراضية
            conn = psycopg2.connect(
                dbname='postgres',
                user=user,
                password=password,
                host=host,
                port=port
            )
            conn.autocommit = True
              # إنشاء cursor للاستعلام
            cursor = conn.cursor()
            
            # استعلام للحصول على قائمة قواعد البيانات مع معلومات إضافية
            cursor.execute("""
                SELECT 
                    d.datname as name,
                    pg_database_size(d.datname) as size,
                    d.encoding,
                    r.rolname as owner
                FROM pg_database d
                LEFT JOIN pg_roles r ON d.datdba = r.oid
                WHERE d.datistemplate = false
                ORDER BY d.datname;
            """)
            
            # تحليل النتيجة
            databases = []
            for row in cursor.fetchall():
                db_name = row[0]
                db_size = row[1] if row[1] else 0
                encoding = row[2] if row[2] else 'UTF8'
                owner = row[3] if row[3] else 'postgres'
                
                if db_name and db_name not in ['postgres', 'template0', 'template1']:
                    # التحقق من كون قاعدة البيانات مسجلة في النظام
                    from ..models import Database
                    is_registered = Database.objects.filter(
                        name=db_name,
                        db_type='postgresql'
                    ).exists()
                    
                    # تحويل الحجم إلى صيغة قابلة للقراءة
                    size_display = self._format_size(db_size)
                    
                    databases.append({
                        'name': db_name,
                        'type': 'postgresql',
                        'size': size_display,
                        'size_bytes': db_size,
                        'encoding': encoding,
                        'owner': owner,
                        'registered': is_registered,
                        'connection_info': {
                            'ENGINE': 'django.db.backends.postgresql',
                            'NAME': db_name,
                            'USER': user,
                            'PASSWORD': password,
                            'HOST': host,
                            'PORT': port,
                        }
                    })
            
            # إغلاق الاتصال            cursor.close()
            conn.close()
            
            # print(f"تم اكتشاف {len(databases)} قاعدة بيانات في PostgreSQL")  # معلومات غير ضرورية
            return databases
            
        except Exception as e:
            print(f"خطأ في اكتشاف قواعد البيانات: {str(e)}")
            # إرجاع قاعدة البيانات الافتراضية على الأقل
            try:
                from django.conf import settings
                current_db_name = settings.DATABASES['default']['NAME']
                return [{
                    'name': current_db_name,
                    'type': 'postgresql',
                    'connection_info': settings.DATABASES['default']
                }]
            except:
                return []

    def sync_discovered_databases(self):
        """مزامنة قواعد البيانات المكتشفة مع النظام"""
        discovered_dbs = self.discover_postgresql_databases()

        if not discovered_dbs:
            return

        synced_count = 0
        for db_info in discovered_dbs:
            try:
                # التحقق من وجود قاعدة البيانات في النظام
                existing_db = Database.objects.filter(
                    name=db_info['name'],
                    db_type='postgresql'
                ).first()

                if not existing_db:
                    # إنشاء قاعدة بيانات جديدة في النظام
                    database = Database.objects.create(
                        name=db_info['name'],
                        db_type='postgresql',
                        connection_info=db_info['connection_info'],
                        is_active=False  # لا نجعلها نشطة تلقائياً
                    )
                    print(f"تم إضافة قاعدة البيانات المكتشفة: {db_info['name']}")
                    synced_count += 1
                else:                    # تحديث معلومات الاتصال إذا لزم الأمر
                    existing_db.connection_info = db_info['connection_info']
                    existing_db.save()
                    # print(f"تم تحديث قاعدة البيانات: {db_info['name']}")  # معلومات غير ضرورية

            except Exception as e:
                print(f"خطأ في مزامنة قاعدة البيانات {db_info['name']}: {str(e)}")

        if synced_count > 0:
            print(f"تم مزامنة {synced_count} قاعدة بيانات جديدة مع النظام")

    def sync_databases_from_settings(self):
        """مزامنة قواعد البيانات من ملف الإعدادات"""
        # إذا كان DATABASE_URL موجود، لا نحتاج لملف الإعدادات
        if os.environ.get('DATABASE_URL'):
            return

        # قراءة ملف الإعدادات
        settings_file = os.path.join(settings.BASE_DIR, 'db_settings.json')
        if not os.path.exists(settings_file):
            # لا نطبع رسالة إذا كان DATABASE_URL موجود
            return

        try:
            with open(settings_file, 'r') as f:
                db_settings = json.load(f)

            # الحصول على قاعدة البيانات النشطة
            active_db_id = db_settings.get('active_db')

            # مزامنة قواعد البيانات
            for db_id, db_info in db_settings.get('databases', {}).items():
                # استخراج معلومات قاعدة البيانات
                engine = db_info.get('ENGINE', '')

                # تحديد نوع قاعدة البيانات من المحرك
                if 'postgresql' in engine:
                    db_type = 'postgresql'
                elif 'sqlite3' in engine:
                    db_type = 'sqlite3'
                else:
                    # تخطي قواعد البيانات غير المدعومة
                    continue

                # استخراج اسم قاعدة البيانات
                db_name = db_info.get('NAME', '')
                if not db_name:
                    # تخطي قواعد البيانات بدون اسم
                    continue

                # إنشاء نسخة من معلومات الاتصال بدون المحرك
                connection_info = {k: v for k, v in db_info.items() if k != 'ENGINE'}

                # التحقق مما إذا كانت قاعدة البيانات موجودة بالفعل
                try:
                    database = Database.objects.get(id=int(db_id))
                    # تحديث قاعدة البيانات الموجودة
                    database.name = os.path.basename(db_name) if db_type == 'sqlite3' else db_name
                    database.db_type = db_type
                    database.connection_info = connection_info
                    database.is_active = (active_db_id == int(db_id))
                    database.save()
                    # print(f"تم تحديث قاعدة البيانات: {database.name}")  # معلومات غير ضرورية
                except Database.DoesNotExist:
                    # إنشاء قاعدة بيانات جديدة
                    database = Database.objects.create(
                        id=int(db_id),
                        name=os.path.basename(db_name) if db_type == 'sqlite3' else db_name,
                        db_type=db_type,
                        connection_info=connection_info,
                        is_active=(active_db_id == int(db_id))
                    )
                    print(f"تم إنشاء قاعدة البيانات: {database.name}")

            print("تمت مزامنة قواعد البيانات بنجاح")
        except Exception as e:
            print(f"حدث خطأ أثناء مزامنة قواعد البيانات: {str(e)}")

    def delete_database(self, database_id):
        """حذف قاعدة بيانات"""
        # الحصول على قاعدة البيانات
        database = Database.objects.get(id=database_id)

        try:
            # حذف قاعدة البيانات حسب النوع
            if database.db_type == 'postgresql':
                # حذف قاعدة بيانات PostgreSQL
                self._delete_postgresql_database(
                    name=database.connection_info.get('NAME', database.name),
                    user=database.connection_info.get('USER', ''),
                    password=database.connection_info.get('PASSWORD', ''),
                    host=database.connection_info.get('HOST', 'localhost'),
                    port=database.connection_info.get('PORT', '5432')
                )
            elif database.db_type == 'sqlite3':
                # حذف قاعدة بيانات SQLite
                self._delete_sqlite_database(
                    name=database.connection_info.get('NAME', f"{database.name}.sqlite3")
                )
        except Exception as e:
            # تسجيل الخطأ ولكن الاستمرار في حذف السجل
            print(f"تحذير: {str(e)}")

        # حذف سجل قاعدة البيانات
        database.delete()

        return True

    def _delete_sqlite_database(self, name):
        """حذف قاعدة بيانات SQLite"""
        # التأكد من وجود الملف
        db_path = os.path.join(settings.BASE_DIR, name)

        # حذف الملف إذا كان موجوداً
        if os.path.exists(db_path):
            os.remove(db_path)

        return True

    def _delete_postgresql_database(self, name, user, password, host, port):
        """حذف قاعدة بيانات PostgreSQL"""
        # التحقق من وجود أداة psql
        if not self._check_command_exists('psql'):
            raise RuntimeError("أداة psql غير موجودة. يرجى التأكد من تثبيت PostgreSQL وإضافته إلى مسار النظام.")

        # التحقق من صحة اسم قاعدة البيانات
        # استبدال الأحرف غير المسموح بها بالشرطة السفلية
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)

        # حذف قاعدة البيانات باستخدام psql
        env = os.environ.copy()
        env['PGPASSWORD'] = password

        # حذف قاعدة البيانات
        drop_cmd = [
            'psql',
            '-h', host,
            '-p', port,
            '-U', user,
            '-c', f"DROP DATABASE IF EXISTS \"{safe_name}\";"
        ]

        try:
            subprocess.run(drop_cmd, env=env, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"فشل حذف قاعدة البيانات: {e.stderr.decode()}")
        except FileNotFoundError:
            raise RuntimeError("أداة psql غير موجودة. يرجى التأكد من تثبيت PostgreSQL وإضافته إلى مسار النظام.")

    def test_connection(self, connection_info):
        """فحص الاتصال بقاعدة البيانات"""
        db_type = connection_info.get('ENGINE', '').split('.')[-1]
        
        try:
            if db_type == 'postgresql':
                return self._test_postgresql_connection(
                    host=connection_info.get('HOST', 'localhost'),
                    port=connection_info.get('PORT', '5432'),
                    user=connection_info.get('USER', ''),
                    password=connection_info.get('PASSWORD', ''),
                    database=connection_info.get('NAME', '')
                )
            elif db_type == 'sqlite3':
                return self._test_sqlite_connection(
                    database_path=connection_info.get('NAME', '')
                )
            else:
                return False, f"نوع قاعدة البيانات غير مدعوم: {db_type}"
        except Exception as e:
            return False, f"خطأ أثناء فحص الاتصال: {str(e)}"

    def _test_postgresql_connection(self, host, port, user, password, database):
        """فحص الاتصال بقاعدة بيانات PostgreSQL"""
        try:
            import psycopg2
            
            # تجربة الاتصال
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                connect_timeout=10
            )
            conn.close()
            return True, "تم الاتصال بنجاح"
        except ImportError:
            return False, "مكتبة psycopg2 غير مثبتة"
        except Exception as e:
            return False, f"فشل الاتصال: {str(e)}"

    def _test_sqlite_connection(self, database_path):
        """فحص الاتصال بقاعدة بيانات SQLite"""
        try:
            # التحقق من وجود الملف أو إمكانية إنشاؤه
            if os.path.exists(database_path):
                # فحص الاتصال بالملف الموجود
                conn = sqlite3.connect(database_path)
                conn.close()
                return True, "تم الاتصال بنجاح"
            else:
                # التحقق من إمكانية إنشاء الملف
                directory = os.path.dirname(database_path)
                if directory and not os.path.exists(directory):
                    return False, f"المجلد غير موجود: {directory}"
                
                # تجربة إنشاء اتصال مؤقت
                conn = sqlite3.connect(database_path)
                conn.close()
                
                # حذف الملف المؤقت إذا تم إنشاؤه
                if os.path.exists(database_path):
                    os.remove(database_path)
                
                return True, "يمكن إنشاء قاعدة البيانات بنجاح"
        except Exception as e:
            return False, f"فشل الاتصال: {str(e)}"

    def create_physical_database(self, connection_info, force_create=False):
        """إنشاء قاعدة البيانات الفعلية فقط (بدون إنشاء سجل Django)"""
        db_type = connection_info.get('ENGINE', '').split('.')[-1] if 'ENGINE' in connection_info else 'postgresql'
        
        try:
            if db_type == 'postgresql':
                # الحصول على اسم قاعدة البيانات في PostgreSQL
                pg_db_name = connection_info.get('NAME', '')
                
                if not pg_db_name:
                    raise ValueError("اسم قاعدة البيانات مطلوب")

                # التحقق من وجود قاعدة البيانات في PostgreSQL إذا كان ذلك ممكنًا
                if not force_create and self._check_postgresql_db_exists(
                    name=pg_db_name,
                    user=connection_info.get('USER', ''),
                    password=connection_info.get('PASSWORD', ''),
                    host=connection_info.get('HOST', 'localhost'),
                    port=connection_info.get('PORT', '5432')
                ):
                    raise ValueError(f"قاعدة البيانات '{pg_db_name}' موجودة بالفعل في PostgreSQL")

                # إنشاء قاعدة البيانات PostgreSQL
                self._create_postgresql_database(
                    name=pg_db_name,
                    user=connection_info.get('USER', ''),
                    password=connection_info.get('PASSWORD', ''),
                    host=connection_info.get('HOST', 'localhost'),
                    port=connection_info.get('PORT', '5432')
                )
                
                print(f"تم إنشاء قاعدة البيانات '{pg_db_name}' في PostgreSQL بنجاح")
                return True, f"تم إنشاء قاعدة البيانات '{pg_db_name}' في PostgreSQL بنجاح"
                
            elif db_type == 'sqlite3':
                # إنشاء قاعدة بيانات SQLite
                sqlite_path = connection_info.get('NAME', '')
                if not sqlite_path:
                    raise ValueError("مسار ملف SQLite مطلوب")
                    
                self._create_sqlite_database(name=sqlite_path)
                print(f"تم إنشاء قاعدة البيانات SQLite '{sqlite_path}' بنجاح")
                return True, f"تم إنشاء قاعدة البيانات SQLite '{sqlite_path}' بنجاح"
            else:
                raise ValueError(f"نوع قاعدة البيانات غير مدعوم: {db_type}")
                
        except Exception as e:
            error_msg = f"فشل في إنشاء قاعدة البيانات: {str(e)}"
            print(error_msg)
            return False, error_msg

    def _format_size(self, size_bytes):
        """تحويل الحجم بالبايت إلى صيغة قابلة للقراءة"""
        if size_bytes == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"

    def check_django_tables(self, database):
        """التحقق من وجود جداول Django الأساسية وتشغيل الترحيلات إذا لزم الأمر"""
        import psycopg2
        try:
            # تجربة الاتصال بقاعدة البيانات
            conn = psycopg2.connect(
                dbname=database.connection_info.get('NAME', database.name),
                user=database.connection_info.get('USER', ''),
                password=database.connection_info.get('PASSWORD', ''),
                host=database.connection_info.get('HOST', 'localhost'),
                port=database.connection_info.get('PORT', '5432'),
                connect_timeout=5
            )
            cursor = conn.cursor()

            # التحقق من وجود جدول django_migrations
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'django_migrations'
                );
            """)
            has_migrations_table = cursor.fetchone()[0]
            
            # التحقق من وجود جدول django_session
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'django_session'
                );
            """)
            has_session_table = cursor.fetchone()[0]

            cursor.close()
            conn.close()

            return {
                'has_migrations_table': has_migrations_table,
                'has_session_table': has_session_table,
                'needs_migrations': not (has_migrations_table and has_session_table)
            }

        except Exception as e:
            print(f"خطأ في التحقق من جداول Django: {str(e)}")
            return {
                'has_migrations_table': False,
                'has_session_table': False,
                'needs_migrations': True,
                'error': str(e)
            }

    def run_migrations(self, database):
        """تشغيل ترحيلات Django على قاعدة البيانات"""
        import subprocess
        import sys
        try:
            # تحضير المتغيرات البيئية
            env = os.environ.copy()
            env['DJANGO_SETTINGS_MODULE'] = 'crm.settings'
            env['DATABASE_URL'] = database.connection_string
            
            # تشغيل الترحيلات
            manage_py = os.path.join(settings.BASE_DIR, 'manage.py')
            result = subprocess.run(
                [sys.executable, manage_py, 'migrate'],
                env=env,
                capture_output=True,
                text=True
            )
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr if result.returncode != 0 else None
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
