from django import forms
from .models import Booking, Route
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']
        
    def __init__(self, *args, **kwargs):
        super(UserRegistrationForm, self).__init__(*args, **kwargs)
        # Add Bootstrap classes to form fields
        for field_name in self.fields:
            self.fields[field_name].widget.attrs.update({'class': 'form-control'})
    
    def save(self, commit=True):
        user = super(UserRegistrationForm, self).save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
        return user

class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = [
            'booking_type', 'full_name', 'contact_number', 'email', 
            'schedule', 'number_of_passengers', 'vehicle_type', 
            'plate_number', 'occupant_count', 'cargo_weight'
        ]
        widgets = {
            'booking_type': forms.Select(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_number': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'schedule': forms.Select(attrs={'class': 'form-control'}),
            'number_of_passengers': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'vehicle_type': forms.Select(attrs={'class': 'form-control'}),
            'plate_number': forms.TextInput(attrs={'class': 'form-control'}),
            'occupant_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'cargo_weight': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '0.1'})
        }

    def clean(self):
        cleaned_data = super().clean()
        booking_type = cleaned_data.get('booking_type')
        
        # Validate vehicle-specific fields if booking type is 'vehicle'
        if booking_type == 'vehicle':
            vehicle_type = cleaned_data.get('vehicle_type')
            plate_number = cleaned_data.get('plate_number')
            
            if not vehicle_type:
                self.add_error('vehicle_type', 'Vehicle type is required for vehicle bookings.')
            
            if not plate_number:
                self.add_error('plate_number', 'Plate number is required for vehicle bookings.')
        
        return cleaned_data

class RouteForm(forms.ModelForm):
    class Meta:
        model = Route
        fields = ['name', 'origin', 'destination', 'distance', 'estimated_duration', 'active', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'origin': forms.TextInput(attrs={'class': 'form-control'}),
            'destination': forms.TextInput(attrs={'class': 'form-control'}),
            'distance': forms.NumberInput(attrs={'class': 'form-control', 'min': 0.1, 'step': '0.1'}),
            'estimated_duration': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
        }
