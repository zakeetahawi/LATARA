# Generated by Django 4.2.21 on 2025-06-28 13:00

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('odoo_db_manager', '0002_alter_googlesheetmapping_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='googlesynctask',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='created_sync_tasks', to=settings.AUTH_USER_MODEL, verbose_name='أنشأ بواسطة'),
        ),
    ]
