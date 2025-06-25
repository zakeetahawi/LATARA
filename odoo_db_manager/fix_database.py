import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from django.db import connection

# Corregir la tabla GoogleSyncConflict
try:
    with connection.cursor() as cursor:
        # Verificar si la columna field_name existe
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='odoo_db_manager_googlesyncconflict' 
            AND column_name='field_name';
        """)
        field_name_exists = cursor.fetchone()
        
        if not field_name_exists:
            print("La columna 'field_name' no existe, creándola...")
            cursor.execute("""
                ALTER TABLE odoo_db_manager_googlesyncconflict 
                ADD COLUMN field_name VARCHAR(100) DEFAULT '';
            """)
            print("Columna 'field_name' creada correctamente")
        else:
            print("La columna 'field_name' ya existe")
            
        # Verificar si la columna row_index existe
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='odoo_db_manager_googlesyncconflict' 
            AND column_name='row_index';
        """)
        row_index_exists = cursor.fetchone()
        
        if not row_index_exists:
            print("La columna 'row_index' no existe, creándola...")
            cursor.execute("""
                ALTER TABLE odoo_db_manager_googlesyncconflict 
                ADD COLUMN row_index INTEGER DEFAULT 0;
            """)
            print("Columna 'row_index' creada correctamente")
        else:
            print("La columna 'row_index' ya existe")
            
        # Verificar si la columna description existe
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='odoo_db_manager_googlesyncconflict' 
            AND column_name='description';
        """)
        description_exists = cursor.fetchone()
        
        if not description_exists:
            print("La columna 'description' no existe, creándola...")
            cursor.execute("""
                ALTER TABLE odoo_db_manager_googlesyncconflict 
                ADD COLUMN description TEXT DEFAULT '';
            """)
            print("Columna 'description' creada correctamente")
        else:
            print("La columna 'description' ya existe")
            
    print("Corrección de la base de datos completada")
    
except Exception as e:
    print(f"Error al corregir la base de datos: {str(e)}")