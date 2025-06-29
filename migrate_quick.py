"""
Quick migration script without Unicode issues
"""

import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'homeupdate.settings')

django.setup()

from django.db import transaction
from odoo_db_manager.google_sync import GoogleSyncConfig
from odoo_db_manager.google_sync_advanced import GoogleSheetMapping
from accounts.models import User

def main():
    print("Starting Google system migration...")
    
    try:
        with transaction.atomic():
            # Get active config
            old_config = GoogleSyncConfig.get_active_config()
            
            if old_config:
                print(f"Found old config: {old_config.name}")
                
                # Check existing mapping
                existing = GoogleSheetMapping.objects.filter(
                    spreadsheet_id=old_config.spreadsheet_id
                ).first()
                
                if not existing:
                    # Create new mapping
                    new_mapping = GoogleSheetMapping.objects.create(
                        name=f"Migrated - {old_config.name}",
                        spreadsheet_id=old_config.spreadsheet_id,
                        sheet_name="Sheet1",
                        target_model="customers.Customer",
                        is_active=old_config.is_active,
                        last_sync=old_config.last_sync,
                        description="Migrated from old system",
                        column_mappings={
                            "A": "customer_name",
                            "B": "customer_phone", 
                            "C": "customer_email",
                            "D": "customer_address"
                        },
                        sync_options={
                            "auto_create_records": True,
                            "update_existing": True,
                            "skip_empty_rows": True,
                            "validate_data": True
                        }
                    )
                    print(f"Created new mapping: {new_mapping.name}")
                else:
                    print(f"Mapping already exists: {existing.name}")
                
                # Deactivate old config
                old_config.is_active = False
                old_config.save()
                print("Deactivated old config")
                
            else:
                print("No active config found")
                
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Migration failed: {str(e)}")

if __name__ == "__main__":
    main()
