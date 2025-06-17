import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url
# تحديد ما إذا كان النظام في وضع الاختبار
TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-9s7)mh5d3y9mz4b9@7@zy77fw!pdv3ivw8p8grp+e=6%ybitj1')

# SECURITY WARNING: don't run with debug turned on in production!
# تفعيل وضع التطوير بشكل دائم للكشف عن الأخطاء
DEBUG = os.environ.get('DEBUG', 'True').lower() in ['true', 't', '1', 'yes', 'y']

# إعداد ALLOWED_HOSTS لدعم جميع المنصات والنطاقات
ALLOWED_HOSTS_DEFAULT = [
    'localhost',
    '127.0.0.1',
    '192.168.2.6',
    '0.0.0.0',
    'testserver',
    # نطاقات الإنتاج
    'latara.uk',
    'www.latara.uk',
    'crm.latara.uk',
    'api.latara.uk',
    'admin.latara.uk',
    # نطاقات Cloudflare
    '*.trycloudflare.com',
    '*.cloudflare.com',
    '*.cfargotunnel.com',
    '*.ngrok.io',
    '*.ngrok-free.app',
]

# دمج ALLOWED_HOSTS من متغير البيئة مع القائمة الافتراضية
env_hosts = os.environ.get('ALLOWED_HOSTS', '').split(',') if os.environ.get('ALLOWED_HOSTS') else []
ALLOWED_HOSTS = list(set(ALLOWED_HOSTS_DEFAULT + env_hosts))  # إزالة التكرارات

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',  # إضافة مكتبة التنسيق البشري
    'widget_tweaks',
    'crispy_forms',  # إضافة مكتبة crispy forms
    'accounts',
    'customers',
    'factory',
    'inspections',
    'installations',
    'inventory',
    'orders',
    'reports',    'odoo_db_manager.apps.OdooDbManagerConfig',  # تطبيق إدارة قواعد البيانات على طراز أودو
    'corsheaders',
    'django_apscheduler', # إضافة مكتبة جدولة المهام
    'dbbackup',  # إضافة تطبيق النسخ الاحتياطي
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist'  # إضافة دعم القائمة السوداء للتوكن
]

# Authentication backends
AUTHENTICATION_BACKENDS = [
    'accounts.backends.CustomModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]


# Debug toolbar معطل مؤقت<|im_start|> لتحسين الأداء

AUTH_USER_MODEL = 'accounts.User'

# قائمة الوسطاء الأساسية (تم تعطيل الوسطاء المخصصة مؤقتاً)
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.gzip.GZipMiddleware',  # استخدام وسيط Django الأساسي
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',    'django.contrib.messages.middleware.MessageMiddleware',    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'crm.middleware.permission_handler.PermissionDeniedMiddleware',
    'odoo_db_manager.middleware.default_user.DefaultUserMiddleware',  # إنشاء مستخدم افتراضي
    # 'crm.middleware.PerformanceMiddleware',  # تم تعطيل مؤقتاً
    # 'crm.middleware.LazyLoadMiddleware',  # تم تعطيل مؤقتاً
]

# تم تعطيل middleware إضافي مؤقتاً لحل مشكلة التحميل
# if DEBUG:
#     MIDDLEWARE.extend([
#         'crm.middleware.QueryPerformanceMiddleware',
#         'crm.middleware.PerformanceCookiesMiddleware',
#     ])

ROOT_URLCONF = 'crm.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.departments',
                'accounts.context_processors.notifications',
                'accounts.context_processors.company_info',
                'accounts.context_processors.footer_settings',
                'accounts.context_processors.system_settings',
                'accounts.context_processors.branch_messages',  # إضافة context processor الجديد
            ],
        },
    },
]

WSGI_APPLICATION = 'crm.wsgi.application'

# تم إزالة إعدادات Channels و Redis لأنها غير مستخدمة
# ASGI_APPLICATION = 'crm.asgi.application'
# CHANNEL_LAYERS = {...}

# Database Configuration (تم تبسيط المنطق)
def get_database_config():
    """تحديد إعدادات قاعدة البيانات"""
    import json    # التكوين الافتراضي - سيتم استخدامه إذا فشلت كل المحاولات الأخرى
    default_config = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'crm_system',
        'USER': 'postgres',
        'PASSWORD': '5525',
        'HOST': 'localhost',
        'PORT': '5432',
    }

    try:
        db_settings_file = os.path.join(BASE_DIR, 'db_settings.json')
        if os.path.exists(db_settings_file):
            with open(db_settings_file, 'r') as f:
                settings_data = json.load(f)
            
            # التحقق من وجود البيانات المطلوبة
            if settings_data and isinstance(settings_data, dict):
                active_db = str(settings_data.get('active_db'))
                if active_db and active_db in settings_data.get('databases', {}):
                    db_config = settings_data['databases'][active_db]                    # التحقق من وجود جميع الحقول المطلوبة
                    required_fields = ['ENGINE', 'NAME', 'USER', 'PASSWORD', 'HOST', 'PORT']
                    if all(field in db_config for field in required_fields):
                        # print(f"قراءة إعدادات قاعدة البيانات من الملف: {db_config}")  # معلومات حساسة
                        # print(f"استخدام قاعدة البيانات: {db_config['NAME']} على {db_config['HOST']}:{db_config['PORT']}")
                        return db_config        # print("استخدام إعدادات قاعدة البيانات الافتراضية")  # معلومات غير ضرورية
        # print(f"الإعدادات الافتراضية: {default_config}")  # معلومات حساسة
        return default_config

    except Exception as e:
        # print(f"خطأ في قراءة إعدادات قاعدة البيانات: {str(e)}")  # معلومات حساسة
        # print("استخدام الإعدادات الافتراضية")  # معلومات غير ضرورية
        return default_config

# تكوين قاعدة البيانات
db_config = get_database_config()

# استخراج TIME_ZONE وإزالته من المعاملات الأساسية لتجنب تمريره إلى PostgreSQL
time_zone = db_config.pop('TIME_ZONE', 'Africa/Cairo')

# إنشاء تكوين نظيف بدون TIME_ZONE
clean_db_config = {k: v for k, v in db_config.items() if k != 'TIME_ZONE'}

DATABASES = {
    'default': {
        'ENGINE': clean_db_config['ENGINE'],
        'NAME': clean_db_config['NAME'],
        'USER': clean_db_config['USER'],
        'PASSWORD': clean_db_config['PASSWORD'],
        'HOST': clean_db_config['HOST'],
        'PORT': clean_db_config['PORT'],
        'ATOMIC_REQUESTS': False,
        'AUTOCOMMIT': True,
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            # إزالة TIME_ZONE من OPTIONS لحل مشكلة PostgreSQL
        },
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'ar'
TIME_ZONE = 'Africa/Cairo'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
# استخدام تخزين أبسط لتجنب مشاكل ملفات source map
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# إعدادات النسخ الاحتياطي
BACKUP_ROOT = os.path.join(BASE_DIR, 'backups')
os.makedirs(BACKUP_ROOT, exist_ok=True)

# استخدام نفس المجلد للملفات المؤقتة والنسخ الاحتياطية
DBBACKUP_TMP_DIR = BACKUP_ROOT
DBBACKUP_STORAGE = 'django.core.files.storage.FileSystemStorage'
DBBACKUP_STORAGE_OPTIONS = {'location': BACKUP_ROOT}
DBBACKUP_CLEANUP_KEEP = 5  # الاحتفاظ بآخر 5 نسخ احتياطية فقط

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication settings
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Cache settings
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,  # 5 minutes
        'OPTIONS': {
            'MAX_ENTRIES': 500,  # تقليل عدد العناصر المخزنة لتوفير الذاكرة
            'CULL_FREQUENCY': 2,  # زيادة تكرار التنظيف
        }
    }
}

# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'crm.auth.CustomJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
}

# إعدادات JWT (Simple JWT)
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),  # زيادة مدة صلاحية التوكن إلى 7 أيام
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),  # زيادة مدة صلاحية توكن التحديث إلى 30 يوم
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_COOKIE': 'access_token',
    'AUTH_COOKIE_HTTP_ONLY': True,
    'AUTH_COOKIE_PATH': '/',
    'AUTH_COOKIE_SAMESITE': 'Lax',
    'AUTH_COOKIE_SECURE': False,  # تعطيل في جميع البيئات لتجنب مشاكل المصادقة
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# Security Settings for Production
if not DEBUG and os.environ.get('ENABLE_SSL_SECURITY', 'false').lower() == 'true':
    # HTTPS/SSL Settings
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # Session and CSRF Settings
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True

    # HSTS Settings
    SECURE_HSTS_SECONDS = 31536000  # سنة واحدة
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Content Security Settings
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

    # Referrer Policy
    SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

    # Cross-Origin Opener Policy
    SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

    # Additional Security Headers
    CSRF_TRUSTED_ORIGINS = [
        'https://localhost',
        'https://127.0.0.1',
    ]

# CORS settings (تم دمج الإعدادات المكررة)
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:5173',  # منفذ Vite الافتراضي
    'http://127.0.0.1:5173',  # منفذ Vite الافتراضي
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    # نطاقات الإنتاج
    'https://latara.uk',
    'https://www.latara.uk',
    'https://crm.latara.uk',
    'https://api.latara.uk',
    'https://admin.latara.uk',
    'http://latara.uk',
    'http://www.latara.uk',
    'http://crm.latara.uk',
    'http://api.latara.uk',
    'http://admin.latara.uk',
]

CORS_ORIGIN_WHITELIST = CORS_ALLOWED_ORIGINS  # استخدام نفس القائمة

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ['*']

CORS_ALLOW_HEADERS = [
    'Authorization',
    'Content-Type',
    'X-CSRFToken',
    'accept',
    'accept-encoding',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-requested-with',
    'x-request-id',
]

# تم دمج إعدادات الأمان أدناه

# Disable CSRF for /api/ endpoints in development
if DEBUG:

    class DisableCSRFMiddleware:
        def __init__(self, get_response):
            self.get_response = get_response

        def __call__(self, request):
            if request.path.startswith('/api/'):
                setattr(request, '_dont_enforce_csrf_checks', True)
            return self.get_response(request)

    MIDDLEWARE.insert(0, 'crm.settings.DisableCSRFMiddleware')

# Security and Session Settings (تم دمج الإعدادات المكررة)
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS + [
    # إضافة نطاقات إضافية للـ CSRF
    'https://latara.uk',
    'https://www.latara.uk',
    'https://crm.latara.uk',
    'https://api.latara.uk',
    'https://admin.latara.uk',
]

# إعدادات CSRF موحدة
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False  # Must be False to allow JavaScript access
CSRF_COOKIE_SECURE = False  # تعطيل لتجنب مشاكل المصادقة
CSRF_USE_SESSIONS = False

# إعدادات Session موحدة
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = False  # تعطيل لتجنب مشاكل المصادقة
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 86400 * 7  # 7 أيام
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# إعدادات جدولة المهام
APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"
APSCHEDULER_RUN_NOW_TIMEOUT = 25  # Seconds

# تكوين المهام المجدولة
SCHEDULER_CONFIG = {
    "apscheduler.jobstores.default": {
        "class": "django_apscheduler.jobstores:DjangoJobStore"
    },
    "apscheduler.executors.processpool": {
        "type": "threadpool",
        "max_workers": 5
    },
    "apscheduler.job_defaults.coalesce": "false",
    "apscheduler.job_defaults.max_instances": "3",
    "apscheduler.timezone": TIME_ZONE,
}

# تكوين مهمة تنظيف الجلسات
SESSION_CLEANUP_SCHEDULE = {
    'days': 1,  # تنظيف الجلسات الأقدم من يوم واحد
    'fix_users': True,  # إصلاح المستخدمين المكررين أيضًا
    'frequency': 'daily',  # تنفيذ المهمة يوميًا
    'hour': 3,  # تنفيذ المهمة في الساعة 3 صباحًا
    'minute': 0,  # تنفيذ المهمة في الدقيقة 0
}

# إعدادات تحسين الأداء
# تقليل عدد الاستعلامات المسموح بها في صفحة واحدة
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# تعطيل التسجيل المفصل في الإنتاج
if not DEBUG:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',  # تغيير مستوى التسجيل إلى INFO للحصول على مزيد من المعلومات
            },
        },
        'loggers': {
            'django': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': True,
            },
            'django.db.backends': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
            'data_management': {  # إضافة تسجيل خاص لتطبيق data_management
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': True,
            },
        },
        'root': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    }

    # تقليل عدد الاتصالات المتزامنة بقاعدة البيانات
    DATABASES['default']['CONN_MAX_AGE'] = 300  # 5 دقائق

    # تعطيل التصحيح التلقائي للمخطط
    DATABASES['default']['AUTOCOMMIT'] = True  # تمكين AUTOCOMMIT لتجنب مشاكل الاتصال

    # تم نقل إعدادات قاعدة بيانات Railway إلى بداية الملف

# ======================================
# Crispy Forms Configuration
# ======================================
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap4"
CRISPY_TEMPLATE_PACK = "bootstrap4"
