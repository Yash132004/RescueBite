from django import forms
from .models import Volunteer, NGO, Donor, Food
from django.contrib.auth.models import User

class FoodDonationForm(forms.ModelForm):
    class Meta:
        model = Food
        fields = ['name', 'food_quantity', 'expiry_hours', 'image']
        widgets = {
            'expiry_hours': forms.NumberInput(attrs={'min': 1, 'max': 72}),
        }

class VolunteerForm(forms.ModelForm):
    # Add an extra field not in the Volunteer model
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Create Password'}))
    
    class Meta:
        model = Volunteer
        # Exclude 'user' because we link it in the view, not the form
        exclude = ['created_at', 'user'] 

class NGOForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Create Password'}))
    
    class Meta:
        model = NGO
        exclude = ['created_at', 'user']

class DonorForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Create Password'}))
    
    class Meta:
        model = Donor
        exclude = ['created_at', 'user']


from .models import Food

class FoodDonationForm(forms.ModelForm):
    class Meta:
        model = Food
        fields = [
            'name',
            'food_quantity',
            'description',
            'expiry_hours',
            'image',
            'pickup_latitude',
            'pickup_longitude',
        ]

        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
