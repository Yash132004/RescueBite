from django import forms

from .models import Food, Donor, NGO, Volunteer


class FoodDonationForm(forms.ModelForm):
    expiry_hours = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'min': 1}),
    )

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

    def clean(self):
        cleaned_data = super().clean()
        pickup_latitude = cleaned_data.get('pickup_latitude')
        pickup_longitude = cleaned_data.get('pickup_longitude')

        if (pickup_latitude is None) != (pickup_longitude is None):
            message = 'Enter both pickup coordinates or leave both blank.'
            if pickup_latitude is None:
                self.add_error('pickup_latitude', message)
            if pickup_longitude is None:
                self.add_error('pickup_longitude', message)

        return cleaned_data


class VolunteerForm(forms.ModelForm):
    # `password` is an extra field: it is not on the model, it is only used
    # by the view to create the auth User. `user` is linked in the view too.
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Create Password'}))

    class Meta:
        model = Volunteer
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
