import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from odoo_db_manager.google_sync_advanced import GoogleSheetMapping

# Crear un mapeo de prueba
try:
    # Verificar si ya existe un mapeo con el nombre "test"
    try:
        mapping = GoogleSheetMapping.objects.get(name="test")
        print(f"Mapeo 'test' ya existe con ID: {mapping.id}")
    except GoogleSheetMapping.DoesNotExist:
        # Crear un nuevo mapeo
        mapping = GoogleSheetMapping.objects.create(
            name="test",
            spreadsheet_id="1Qs9tN3XZ8F8F8F8F8F8F8F8F8F8F8F8F8F8F8F8F8F8",
            sheet_name="Sheet1",
            header_row=1,
            start_row=2,
            column_mappings={
                "A": "customer_code",
                "B": "customer_name",
                "C": "customer_phone",
                "D": "customer_email",
                "E": "order_number",
                "F": "order_status"
            },
            auto_create_customers=True,
            auto_create_orders=True,
            update_existing_customers=True,
            update_existing_orders=True
        )
        print(f"Mapeo 'test' creado con ID: {mapping.id}")
        
    # Mostrar detalles del mapeo
    print(f"Detalles del mapeo:")
    print(f"  - Nombre: {mapping.name}")
    print(f"  - ID de la hoja: {mapping.spreadsheet_id}")
    print(f"  - Nombre de la hoja: {mapping.sheet_name}")
    print(f"  - Fila de encabezados: {mapping.header_row}")
    print(f"  - Fila de inicio: {mapping.start_row}")
    print(f"  - Mapeos de columnas: {mapping.column_mappings}")
    
except Exception as e:
    print(f"Error: {str(e)}")