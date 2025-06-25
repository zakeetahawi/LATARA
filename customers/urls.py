from django.urls import path
from . import views
from .views import CustomerDashboardView

app_name = 'customers'

urlpatterns = [
    # Customer list as main page
    path('', views.customer_list, name='customer_list'),

    # Old dashboard (deactivated)
    path('dashboard/', CustomerDashboardView.as_view(), name='dashboard'),
    path('<int:pk>/', views.customer_detail, name='customer_detail'),
    path('create/', views.customer_create, name='customer_create'),
    path('<int:pk>/update/', views.customer_update, name='customer_update'),
    path('<int:pk>/delete/', views.customer_delete, name='customer_delete'),

    # Note Management
    path('<int:pk>/add-note/', views.add_customer_note, name='add_note'),
    path('<int:customer_pk>/notes/<int:note_pk>/delete/', views.delete_customer_note, name='delete_note'),

    # Category Management
    path('categories/', views.customer_category_list, name='category_list'),
    path('categories/add/', views.add_customer_category, name='add_category'),

    # API path to find customer by phone number
    path('find-by-phone/', views.find_customer_by_phone, name='find_customer_by_phone'),
]
