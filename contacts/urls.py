from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('contacts/', views.contact_list, name='contact_list'),
    path('contacts/add/', views.add_contact, name='add_contact'),
    path('contacts/<int:contact_id>/edit/', views.edit_contact, name='edit_contact'),
    path('contacts/<int:contact_id>/delete/', views.delete_contact, name='delete_contact'),
    path('import-export/', views.import_export, name='import_export'),
    path('settings/', views.settings_view, name='settings'),
    path('settings/merge/', views.merge_contacts, name='merge_contacts'),
    path('settings/dismiss-duplicates/', views.dismiss_duplicates, name='dismiss_duplicates'),
    path('settings/add-category/', views.add_category, name='add_category'),
    path('settings/delete-category/<int:category_id>/', views.delete_category, name='delete_category'),
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('admin-panel/users/', views.admin_users, name='admin_users'),
    path('admin-panel/users/<int:user_id>/toggle/', views.admin_toggle_user, name='admin_toggle_user'),
    path('admin-panel/contacts/', views.admin_contacts, name='admin_contacts'),
    path('admin-panel/export/', views.admin_export_all, name='admin_export_all'),
]