/**
 * وظائف JavaScript لنظام الاستيراد المحسن من Google Sheets
 */

// متغيرات عامة
let currentFormData = {};
let availableSheets = [];

// تهيئة النظام عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    initializeImportSystem();
});

/**
 * تهيئة نظام الاستيراد
 */
function initializeImportSystem() {
    // تهيئة النماذج
    initializeForms();
    
    // تهيئة مستمعي الأحداث
    setupEventListeners();
    
    // تهيئة العناصر التفاعلية
    initializeInteractiveElements();
}

/**
 * تهيئة النماذج
 */
function initializeForms() {
    const importForm = document.getElementById('importForm');
    if (importForm) {
        // إعداد التحقق من صحة النموذج
        setupFormValidation(importForm);
        
        // إعداد إرسال النموذج
        setupFormSubmission(importForm);
    }
}

/**
 * إعداد مستمعي الأحداث
 */
function setupEventListeners() {
    // مستمع لتغيير خيار "استيراد جميع البيانات"
    const importAllCheckbox = document.getElementById('import_all_checkbox');
    if (importAllCheckbox) {
        importAllCheckbox.addEventListener('change', toggleRangeFields);
    }
    
    // مستمع لتغيير اختيار الصفحة
    const sheetSelect = document.getElementById('sheet_name_select');
    if (sheetSelect) {
        sheetSelect.addEventListener('change', updateSheetPreview);
    }
    
    // مستمع لتحديث معرف الجدول
    const spreadsheetIdInput = document.getElementById('spreadsheet_id_input');
    if (spreadsheetIdInput) {
        spreadsheetIdInput.addEventListener('blur', refreshSheetsIfNeeded);
    }
}

/**
 * تهيئة العناصر التفاعلية
 */
function initializeInteractiveElements() {
    // تطبيق الحالة الأولية للنطاق
    toggleRangeFields();
    
    // تحديث معاينة الصفحة
    updateSheetPreview();
    
    // تهيئة أشرطة التقدم المتحركة
    initializeProgressBars();
}

/**
 * تبديل عرض حقول النطاق
 */
function toggleRangeFields() {
    const importAllCheckbox = document.getElementById('import_all_checkbox');
    const rangeFields = document.getElementById('rangeFields');
    
    if (!importAllCheckbox || !rangeFields) return;
    
    if (importAllCheckbox.checked) {
        rangeFields.classList.remove('show');
        // إلغاء اشتراط حقول النطاق
        setRangeFieldsRequired(false);
    } else {
        rangeFields.classList.add('show');
        // جعل حقول النطاق مطلوبة
        setRangeFieldsRequired(true);
    }
}

/**
 * تعيين حقول النطاق كمطلوبة أو اختيارية
 */
function setRangeFieldsRequired(required) {
    const startRowInput = document.getElementById('start_row_input');
    const endRowInput = document.getElementById('end_row_input');
    
    if (startRowInput) {
        startRowInput.required = required;
    }
    if (endRowInput) {
        endRowInput.required = required;
    }
}

/**
 * تحديث معاينة الصفحة المحددة
 */
function updateSheetPreview() {
    const sheetSelect = document.getElementById('sheet_name_select');
    const preview = document.getElementById('sheetPreview');
    
    if (!sheetSelect || !preview) return;
    
    if (sheetSelect.value) {
        const selectedOption = sheetSelect.options[sheetSelect.selectedIndex];
        const sheetTitle = selectedOption.text;
        
        preview.innerHTML = `
            <i class="fas fa-table text-success"></i>
            <h6 class="mt-2 mb-1">${escapeHtml(sheetTitle)}</h6>
            <p class="text-muted mb-0">جاهز للاستيراد</p>
        `;
        preview.style.display = 'block';
        
        // إضافة تأثير الحركة
        preview.style.opacity = '0';
        preview.style.transform = 'translateY(20px)';
        setTimeout(() => {
            preview.style.transition = 'all 0.3s ease';
            preview.style.opacity = '1';
            preview.style.transform = 'translateY(0)';
        }, 100);
    } else {
        preview.style.display = 'none';
    }
}

/**
 * تحديث قائمة الصفحات إذا لزم الأمر
 */
function refreshSheetsIfNeeded() {
    const spreadsheetId = document.getElementById('spreadsheet_id_input')?.value;
    
    if (spreadsheetId && spreadsheetId.length === 44) {
        // إظهار مؤشر التحميل
        showLoadingIndicator('جارٍ تحديث قائمة الصفحات...');
        
        // جلب قائمة الصفحات
        fetchSheets(spreadsheetId)
            .then(sheets => {
                updateSheetsDropdown(sheets);
                hideLoadingIndicator();
                showMessage('تم تحديث قائمة الصفحات بنجاح', 'success');
            })
            .catch(error => {
                hideLoadingIndicator();
                showMessage('فشل في تحديث قائمة الصفحات: ' + error.message, 'error');
            });
    }
}

/**
 * جلب قائمة الصفحات من الخادم
 */
async function fetchSheets(spreadsheetId) {
    const response = await fetch(`/odoo-db-manager/google-import/api/sheets/?spreadsheet_id=${encodeURIComponent(spreadsheetId)}`);
    
    if (!response.ok) {
        throw new Error('فشل في الاتصال بالخادم');
    }
    
    const data = await response.json();
    
    if (!data.success) {
        throw new Error(data.error || 'حدث خطأ غير معروف');
    }
    
    return data.sheets;
}

/**
 * تحديث القائمة المنسدلة للصفحات
 */
function updateSheetsDropdown(sheets) {
    const sheetSelect = document.getElementById('sheet_name_select');
    if (!sheetSelect) return;
    
    // حفظ القيمة المحددة حالياً
    const currentValue = sheetSelect.value;
    
    // مسح الخيارات الحالية
    sheetSelect.innerHTML = '<option value="">-- اختر صفحة --</option>';
    
    // إضافة الصفحات الجديدة
    sheets.forEach(sheet => {
        const option = document.createElement('option');
        option.value = sheet.title;
        option.textContent = `${sheet.title} (${sheet.row_count} صف)`;
        sheetSelect.appendChild(option);
    });
    
    // استعادة القيمة المحددة إذا كانت لا تزال متاحة
    if (currentValue && sheetSelect.querySelector(`option[value="${currentValue}"]`)) {
        sheetSelect.value = currentValue;
    }
    
    // تحديث المعاينة
    updateSheetPreview();
}

/**
 * استخراج معرف الجدول من الرابط
 */
function extractSpreadsheetId(url) {
    const input = document.getElementById('spreadsheet_id_input');
    if (!input || !url) return;
    
    const match = url.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
    if (match) {
        input.value = match[1];
        refreshSheetsIfNeeded();
    }
}

/**
 * معاينة البيانات
 */
function previewData() {
    const form = document.getElementById('importForm');
    if (!form) return;
    
    // التحقق من صحة النموذج
    if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }
    
    // إظهار نافذة المعاينة
    const modal = new bootstrap.Modal(document.getElementById('previewModal'));
    modal.show();
    
    // محاكاة جلب البيانات (يمكن استبدالها بطلب AJAX حقيقي)
    const sheetName = document.getElementById('sheet_name_select')?.value;
    const importAll = document.getElementById('import_all_checkbox')?.checked;
    
    setTimeout(() => {
        document.getElementById('previewContent').innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i>
                هذه معاينة سريعة. سيتم عرض البيانات الفعلية في الخطوة التالية.
            </div>
            <p>الصفحة المحددة: <strong>${escapeHtml(sheetName)}</strong></p>
            <p>نوع الاستيراد: <strong>${importAll ? 'جميع البيانات' : 'نطاق محدد'}</strong></p>
        `;
    }, 1000);
}

/**
 * إعادة تعيين النموذج
 */
function resetForm() {
    const form = document.getElementById('importForm');
    if (!form) return;
    
    // إعادة تعيين النموذج
    form.reset();
    
    // تطبيق الحالات الافتراضية
    toggleRangeFields();
    updateSheetPreview();
    
    // إظهار رسالة تأكيد
    showMessage('تم إعادة تعيين النموذج', 'info');
}

/**
 * إعداد التحقق من صحة النموذج
 */
function setupFormValidation(form) {
    form.addEventListener('submit', function(event) {
        if (!form.checkValidity()) {
            event.preventDefault();
            event.stopPropagation();
            
            // إظهار رسالة خطأ
            showMessage('يرجى إكمال جميع الحقول المطلوبة', 'error');
        }
        
        form.classList.add('was-validated');
    });
}

/**
 * إعداد إرسال النموذج
 */
function setupFormSubmission(form) {
    form.addEventListener('submit', function(event) {
        if (form.checkValidity()) {
            // إظهار مؤشر التحميل
            showLoadingIndicator('جارٍ معالجة البيانات...');
            
            // تأخير بسيط لإظهار المؤشر
            setTimeout(() => {
                form.submit();
            }, 500);
        }
    });
}

/**
 * تهيئة أشرطة التقدم المتحركة
 */
function initializeProgressBars() {
    const progressBars = document.querySelectorAll('.progress-bar');
    progressBars.forEach(bar => {
        const width = bar.style.width;
        bar.style.width = '0%';
        setTimeout(() => {
            bar.style.transition = 'width 1s ease-in-out';
            bar.style.width = width;
        }, 500);
    });
}

/**
 * إظهار مؤشر التحميل
 */
function showLoadingIndicator(message = 'جارٍ التحميل...') {
    // إنشاء عنصر التحميل إذا لم يكن موجوداً
    let loadingEl = document.getElementById('loadingIndicator');
    if (!loadingEl) {
        loadingEl = document.createElement('div');
        loadingEl.id = 'loadingIndicator';
        loadingEl.className = 'loading-overlay';
        loadingEl.innerHTML = `
            <div class="loading-content">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2 mb-0" id="loadingMessage">${message}</p>
            </div>
        `;
        document.body.appendChild(loadingEl);
    } else {
        document.getElementById('loadingMessage').textContent = message;
    }
    
    loadingEl.style.display = 'flex';
}

/**
 * إخفاء مؤشر التحميل
 */
function hideLoadingIndicator() {
    const loadingEl = document.getElementById('loadingIndicator');
    if (loadingEl) {
        loadingEl.style.display = 'none';
    }
}

/**
 * إظهار رسالة للمستخدم
 */
function showMessage(message, type = 'info') {
    // إنشاء عنصر الرسالة
    const alertEl = document.createElement('div');
    alertEl.className = `alert alert-${getBootstrapAlertClass(type)} alert-dismissible fade show`;
    alertEl.style.position = 'fixed';
    alertEl.style.top = '20px';
    alertEl.style.right = '20px';
    alertEl.style.zIndex = '9999';
    alertEl.style.minWidth = '300px';
    
    alertEl.innerHTML = `
        <i class="fas fa-${getIconClass(type)}"></i>
        ${escapeHtml(message)}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertEl);
    
    // إزالة الرسالة تلقائياً بعد 5 ثوانٍ
    setTimeout(() => {
        if (alertEl.parentNode) {
            alertEl.remove();
        }
    }, 5000);
}

/**
 * الحصول على فئة تنبيه Bootstrap
 */
function getBootstrapAlertClass(type) {
    const classes = {
        'success': 'success',
        'error': 'danger',
        'warning': 'warning',
        'info': 'info'
    };
    return classes[type] || 'info';
}

/**
 * الحصول على فئة الأيقونة
 */
function getIconClass(type) {
    const icons = {
        'success': 'check-circle',
        'error': 'exclamation-circle',
        'warning': 'exclamation-triangle',
        'info': 'info-circle'
    };
    return icons[type] || 'info-circle';
}

/**
 * تجنب هجمات XSS بتشفير HTML
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

// إضافة أنماط CSS لمؤشر التحميل
const loadingStyles = `
    .loading-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        display: none;
        justify-content: center;
        align-items: center;
        z-index: 10000;
    }
    
    .loading-content {
        background: white;
        padding: 30px;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
    }
    
    .range-fields {
        display: none;
        animation: fadeIn 0.3s ease;
    }
    
    .range-fields.show {
        display: block;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-10px); }
        to { opacity: 1; transform: translateY(0); }
    }
`;

// إضافة الأنماط إلى الصفحة
const styleSheet = document.createElement('style');
styleSheet.textContent = loadingStyles;
document.head.appendChild(styleSheet);
