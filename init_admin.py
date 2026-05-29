# init_admin.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User

try:
    if not User.objects.filter(username='admin').exists():
        u = User.objects.create_user(
            username='admin', 
            email='admin@contactbook.com', 
            password='admin1234'
        )
        u.profile.role = 'admin'
        u.profile.save()
        print("Admin user created successfully.")
    else:
        print("Admin user already exists. Skipping.")
except Exception as e:
    print(f"Error creating admin: {e}")