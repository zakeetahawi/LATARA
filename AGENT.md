# CRM System Development Guide

## Build & Development Commands
- `python manage.py runserver` - Start development server
- `python manage.py test` - Run all tests
- `python manage.py test <app_name>` - Run tests for specific app
- `python manage.py migrate` - Apply database migrations
- `python manage.py makemigrations` - Create new migrations
- `python manage.py collectstatic` - Collect static files
- `python manage.py dbbackup` - Create database backup

## Architecture Overview
Django 4.2 CRM system with PostgreSQL database. Main apps: accounts (auth/users), customers, orders, inventory, inspections, installations, factory, reports, odoo_db_manager. Uses REST framework with JWT auth, Google Sheets integration, and APScheduler for background tasks.

## Code Style & Conventions
- Arabic language system (RTL): Use Arabic verbose names and help text
- Model naming: PascalCase classes, snake_case fields
- Views: Class-based views preferred, function views for simple cases
- Forms: Use crispy_forms with bootstrap4 templates
- URL patterns: Include app namespace, use kebab-case
- Database: Use ForeignKey with PROTECT/CASCADE appropriately
- Imports: Django imports first, then third-party, then local apps
- Error handling: Use ValidationError for model validation, proper exception handling in views
