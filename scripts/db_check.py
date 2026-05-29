import os
import sys
from pathlib import Path
import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))  # ensures smartcontact is importable

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

django.setup()

from django.contrib.auth.models import User
from contacts.models import Category, Contact, ImportLog

print(f"Users:       {User.objects.count()}")
print(f"Categories:  {Category.objects.count()}")
print(f"Contacts:    {Contact.objects.count()}")
print(f"ImportLogs:  {ImportLog.objects.count()}")
print(f"\nDefault categories:")
for c in Category.objects.filter(user=None):
    print(f"  - {c.name}")