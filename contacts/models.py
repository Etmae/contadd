from django.db import models
from django.contrib.auth.models import User


class Category(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='categories',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def is_default(self):
        return self.user is None


class Contact(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contacts')
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contacts',
    )
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    image = models.ImageField(upload_to='contact_images/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return f"{self.full_name} ({self.user.username})"

    def get_initials(self):
        parts = self.full_name.strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        elif len(parts) == 1:
            return parts[0][0].upper()
        return '?'

    def get_avatar_color(self):
        colors = [
            '#4F86C6', '#E07B54', '#5BAD8F', '#9B7FD4',
            '#D4736A', '#6AAFD4', '#D4A96A', '#7FBD6A',
        ]
        index = sum(ord(c) for c in self.full_name) % len(colors)
        return colors[index]


class ImportLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='import_logs')
    imported_count = models.IntegerField(default=0)
    skipped_duplicates = models.IntegerField(default=0)
    failed_rows = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Import by {self.user.username} at {self.created_at:%Y-%m-%d %H:%M}"