# Generated manually to support common production lookup paths.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0002_contact_image'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='category',
            index=models.Index(fields=['user', 'name'], name='category_user_name_idx'),
        ),
        migrations.AddIndex(
            model_name='contact',
            index=models.Index(fields=['user', 'full_name'], name='contact_user_name_idx'),
        ),
        migrations.AddIndex(
            model_name='contact',
            index=models.Index(fields=['user', 'phone_number'], name='contact_user_phone_idx'),
        ),
        migrations.AddIndex(
            model_name='contact',
            index=models.Index(fields=['user', 'email'], name='contact_user_email_idx'),
        ),
        migrations.AddIndex(
            model_name='contact',
            index=models.Index(fields=['user', 'created_at'], name='contact_user_created_idx'),
        ),
        migrations.AddIndex(
            model_name='contact',
            index=models.Index(fields=['category'], name='contact_category_idx'),
        ),
    ]
