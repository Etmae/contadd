import os
import sys
from pathlib import Path
import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))  # ensures smartcontact is importable

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

django.setup()

from contacts.models import Category

DEFAULT_CATEGORIES = ['Family', 'Friends', 'Work', 'Business', 'School']

def seed_categories():
    created_count = 0
    for name in DEFAULT_CATEGORIES:
        obj, created = Category.objects.get_or_create(name=name, user=None)
        if created:
            created_count += 1
            print(f"  Created: {name}")
        else:
            print(f"  Already exists: {name}")
    print(f"\nDone. {created_count} new categories created.")

if __name__ == '__main__':
    seed_categories()



