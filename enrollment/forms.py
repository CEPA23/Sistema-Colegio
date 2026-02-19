from django import forms

from .models import Enrollment


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ['student', 'academic_year', 'section', 'status']
