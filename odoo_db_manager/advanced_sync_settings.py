"""
إعدادات المزامنة المتقدمة مع Google Sheets
Advanced Google Sheets Sync Settings
"""

from django.conf import settings

# إعدادات المزامنة الافتراضية
ADVANCED_SYNC_SETTINGS = {
    # إعدادات عامة
    'ENABLE_ADVANCED_SYNC': True,
    'MAX_CONCURRENT_SYNCS': 3,
    'SYNC_TIMEOUT_MINUTES': 30,
    'MAX_ROWS_PER_SYNC': 10000,
    
    # إعدادات إعادة المحاولة
    'MAX_RETRIES': 3,
    'RETRY_DELAY_SECONDS': 60,
    'EXPONENTIAL_BACKOFF': True,
    
    # إعدادات التخزين المؤقت
    'CACHE_SHEET_DATA': True,
    'CACHE_TIMEOUT_MINUTES': 15,
    'CACHE_KEY_PREFIX': 'advanced_sync',
    
    # إعدادات التنظيف
    'AUTO_CLEANUP_TASKS': True,
    'KEEP_COMPLETED_TASKS_DAYS': 30,
    'KEEP_FAILED_TASKS_DAYS': 90,
    
    # إعدادات الإشعارات
    'SEND_EMAIL_NOTIFICATIONS': True,
    'SEND_SUCCESS_NOTIFICATIONS': False,
    'SEND_ERROR_NOTIFICATIONS': True,
    'NOTIFICATION_EMAIL_TEMPLATE': 'odoo_db_manager/emails/sync_notification.html',
    
    # إعدادات الأمان
    'VALIDATE_SHEET_ACCESS': True,
    'REQUIRE_HTTPS': True,
    'LOG_SENSITIVE_DATA': False,
    
    # إعدادات الأداء
    'BATCH_SIZE': 100,
    'USE_BULK_CREATE': True,
    'USE_BULK_UPDATE': True,
    'OPTIMIZE_QUERIES': True,
    
    # إعدادات التعارضات
    'AUTO_RESOLVE_CONFLICTS': False,
    'CONFLICT_RESOLUTION_STRATEGY': 'manual',  # manual, system_wins, sheet_wins
    'MAX_CONFLICTS_PER_SYNC': 100,
    
    # إعدادات المزامنة العكسية
    'ENABLE_REVERSE_SYNC': True,
    'REVERSE_SYNC_BATCH_SIZE': 50,
    'REVERSE_SYNC_FIELDS_LIMIT': 20,
    
    # إعدادات الجدولة
    'MIN_SCHEDULE_INTERVAL_MINUTES': 5,
    'MAX_SCHEDULE_INTERVAL_MINUTES': 1440,  # 24 hours
    'DEFAULT_SCHEDULE_INTERVAL_MINUTES': 60,
    
    # إعدادات التسجيل
    'LOG_LEVEL': 'INFO',
    'LOG_TO_FILE': True,
    'LOG_FILE_PATH': 'logs/advanced_sync.log',
    'LOG_ROTATION': True,
    'LOG_MAX_SIZE_MB': 10,
    'LOG_BACKUP_COUNT': 5,
    
    # إعدادات Google Sheets API
    'GOOGLE_SHEETS_API_VERSION': 'v4',
    'GOOGLE_SHEETS_SCOPES': [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.readonly'
    ],
    'GOOGLE_API_RATE_LIMIT': 100,  # requests per 100 seconds
    'GOOGLE_API_QUOTA_USER': None,
    
    # إعدادات التحقق من البيانات
    'VALIDATE_DATA_TYPES': True,
    'VALIDATE_REQUIRED_FIELDS': True,
    'VALIDATE_FIELD_LENGTHS': True,
    'SKIP_INVALID_ROWS': True,
    
    # إعدادات التحويل
    'AUTO_CONVERT_DATES': True,
    'DATE_FORMATS': [
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%m/%d/%Y',
        '%d-%m-%Y',
        '%Y/%m/%d'
    ],
    'AUTO_CONVERT_NUMBERS': True,
    'DECIMAL_SEPARATOR': '.',
    'THOUSANDS_SEPARATOR': ',',
    
    # إعدادات النص
    'TRIM_WHITESPACE': True,
    'NORMALIZE_UNICODE': True,
    'DEFAULT_ENCODING': 'utf-8',
    'HANDLE_EMPTY_STRINGS': True,
    'EMPTY_STRING_AS_NULL': False,
    
    # إعدادات الحقول المخصصة
    'ALLOW_CUSTOM_FIELDS': False,
    'CUSTOM_FIELD_PREFIX': 'custom_',
    'MAX_CUSTOM_FIELDS': 10,
    
    # إعدادات التقارير
    'GENERATE_SYNC_REPORTS': True,
    'REPORT_FORMAT': 'html',  # html, pdf, excel
    'INCLUDE_STATISTICS': True,
    'INCLUDE_ERROR_DETAILS': True,
    
    # إعدادات المراقبة
    'ENABLE_MONITORING': True,
    'MONITOR_PERFORMANCE': True,
    'MONITOR_MEMORY_USAGE': True,
    'PERFORMANCE_THRESHOLD_SECONDS': 300,  # 5 minutes
    
    # إعدادات النسخ الاحتياطي
    'BACKUP_BEFORE_SYNC': False,
    'BACKUP_RETENTION_DAYS': 7,
    'BACKUP_COMPRESSION': True,
    
    # إعدادات التكامل
    'WEBHOOK_NOTIFICATIONS': False,
    'WEBHOOK_URL': None,
    'WEBHOOK_SECRET': None,
    'SLACK_NOTIFICATIONS': False,
    'SLACK_WEBHOOK_URL': None,
}

# دمج الإعدادات مع إعدادات Django
def get_sync_setting(key, default=None):
    """الحصول على إعداد المزامنة"""
    # البحث في إعدادات Django أولاً
    django_key = f'ADVANCED_SYNC_{key}'
    if hasattr(settings, django_key):
        return getattr(settings, django_key)
    
    # البحث في الإعدادات الافتراضية
    return ADVANCED_SYNC_SETTINGS.get(key, default)

# إعدادات التسجيل المخصصة
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'advanced_sync': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'advanced_sync_file': {
            'level': get_sync_setting('LOG_LEVEL', 'INFO'),
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': get_sync_setting('LOG_FILE_PATH', 'logs/advanced_sync.log'),
            'maxBytes': get_sync_setting('LOG_MAX_SIZE_MB', 10) * 1024 * 1024,
            'backupCount': get_sync_setting('LOG_BACKUP_COUNT', 5),
            'formatter': 'advanced_sync',
        },
        'advanced_sync_console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'advanced_sync',
        },
    },
    'loggers': {
        'odoo_db_manager.advanced_sync': {
            'handlers': ['advanced_sync_file', 'advanced_sync_console'],
            'level': get_sync_setting('LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}

# تطبيق إعدادات التسجيل
if get_sync_setting('LOG_TO_FILE', True):
    import logging.config
    import os
    
    # إنشاء مجلد السجلات إذا لم يكن موجوداً
    log_dir = os.path.dirname(get_sync_setting('LOG_FILE_PATH', 'logs/advanced_sync.log'))
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    logging.config.dictConfig(LOGGING_CONFIG)

# إعدادات Celery للمزامنة المتقدمة
CELERY_ADVANCED_SYNC_SETTINGS = {
    'task_serializer': 'json',
    'accept_content': ['json'],
    'result_serializer': 'json',
    'timezone': 'Asia/Riyadh',
    'enable_utc': True,
    
    # إعدادات المهام
    'task_soft_time_limit': get_sync_setting('SYNC_TIMEOUT_MINUTES', 30) * 60,
    'task_time_limit': get_sync_setting('SYNC_TIMEOUT_MINUTES', 30) * 60 + 60,
    'task_max_retries': get_sync_setting('MAX_RETRIES', 3),
    'task_default_retry_delay': get_sync_setting('RETRY_DELAY_SECONDS', 60),
    
    # إعدادات الأداء
    'worker_prefetch_multiplier': 1,
    'task_acks_late': True,
    'worker_disable_rate_limits': False,
    
    # إعدادات المراقبة
    'worker_send_task_events': True,
    'task_send_sent_event': True,
    'task_track_started': True,
    
    # إعدادات النتائج
    'result_expires': 3600,  # hour
    'result_persistent': True,
    
    # إعدادات الجدولة
    'beat_schedule': {
        'run-scheduled-syncs': {
            'task': 'odoo_db_manager.tasks.run_scheduled_syncs',
            'schedule': 300.0,  # 5 minutes
        },
        'cleanup-old-tasks': {
            'task': 'odoo_db_manager.tasks.cleanup_old_tasks',
            'schedule': 86400.0,  # 24 hours
        },
        'validate-mappings': {
            'task': 'odoo_db_manager.tasks.validate_all_mappings',
            'schedule': 3600.0,  # 1 hour
        },
    },
}

# دوال مساعدة للإعدادات
def is_advanced_sync_enabled():
    """التحقق من تفعيل المزامنة المتقدمة"""
    return get_sync_setting('ENABLE_ADVANCED_SYNC', True)

def get_max_concurrent_syncs():
    """الحصول على الحد الأقصى للمزامنة المتزامنة"""
    return get_sync_setting('MAX_CONCURRENT_SYNCS', 3)

def get_sync_timeout():
    """الحصول على مهلة المزامنة بالثواني"""
    return get_sync_setting('SYNC_TIMEOUT_MINUTES', 30) * 60

def should_send_notifications():
    """التحقق من إرسال الإشعارات"""
    return get_sync_setting('SEND_EMAIL_NOTIFICATIONS', True)

def get_batch_size():
    """الحصول على حجم الدفعة"""
    return get_sync_setting('BATCH_SIZE', 100)

def get_cache_timeout():
    """الحصول على مهلة التخزين المؤقت بالثواني"""
    return get_sync_setting('CACHE_TIMEOUT_MINUTES', 15) * 60

def get_conflict_resolution_strategy():
    """الحصول على استراتيجية حل التعارضات"""
    return get_sync_setting('CONFLICT_RESOLUTION_STRATEGY', 'manual')

def is_reverse_sync_enabled():
    """التحقق من تفعيل المزامنة العكسية"""
    return get_sync_setting('ENABLE_REVERSE_SYNC', True)

def get_date_formats():
    """الحصول على تنسيقات التاريخ المدعومة"""
    return get_sync_setting('DATE_FORMATS', [
        '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d'
    ])

def should_validate_data():
    """التحقق من تفعيل التحقق من البيانات"""
    return get_sync_setting('VALIDATE_DATA_TYPES', True)

def get_google_api_rate_limit():
    """الحصول على حد معدل Google API"""
    return get_sync_setting('GOOGLE_API_RATE_LIMIT', 100)

# تصدير الإعدادات للاستخدام في التطبيق
__all__ = [
    'ADVANCED_SYNC_SETTINGS',
    'get_sync_setting',
    'is_advanced_sync_enabled',
    'get_max_concurrent_syncs',
    'get_sync_timeout',
    'should_send_notifications',
    'get_batch_size',
    'get_cache_timeout',
    'get_conflict_resolution_strategy',
    'is_reverse_sync_enabled',
    'get_date_formats',
    'should_validate_data',
    'get_google_api_rate_limit',
    'CELERY_ADVANCED_SYNC_SETTINGS',
]
