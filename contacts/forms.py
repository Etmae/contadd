from django import forms
from django.db.models import Q
from .models import Contact, Category


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['full_name', 'phone_number', 'email', 'category', 'image']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'placeholder': 'e.g. John Doe',
                'class': 'w-full pl-10 pr-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50 focus:bg-white transition-all'
            }),
            'phone_number': forms.TextInput(attrs={
                'placeholder': 'e.g. 08012345678',
                'class': 'w-full pl-10 pr-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50 focus:bg-white transition-all'
            }),
            'email': forms.EmailInput(attrs={
                'placeholder': 'e.g. john@example.com',
                'class': 'w-full pl-10 pr-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50 focus:bg-white transition-all'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full pl-10 pr-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50 focus:bg-white transition-all appearance-none'
            }),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(
            Q(user=None) | Q(user=user)
        )
        self.fields['category'].empty_label = 'No category'
        self.fields['image'].required = False
        self.fields['email'].required = False

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            if image.size > 1 * 1024 * 1024:
                raise forms.ValidationError('Image must be smaller than 1MB.')
        return image