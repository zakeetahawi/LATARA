
document.addEventListener('DOMContentLoaded', function() {
    const importType = document.getElementById('id_import_type');
    const rangeFields = document.getElementById('range_fields');
    const startRow = document.getElementById('id_start_row');
    const endRow = document.getElementById('id_end_row');

    function toggleRangeFields() {
        if (importType.value === 'range') {
            rangeFields.style.display = 'block';
            startRow.required = true;
            endRow.required = true;
        } else {
            rangeFields.style.display = 'none';
            startRow.required = false;
            endRow.required = false;
        }
    }

    if (importType) {
        importType.addEventListener('change', toggleRangeFields);
        // Initial check
        toggleRangeFields();
    }
});
