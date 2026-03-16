from django import forms

from academic.models import AcademicYear
from .models import Enrollment


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ['student', 'academic_year', 'section', 'status']


class StudentBulkImportForm(forms.Form):
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.select_related('school').order_by('-year'),
        label='Anio academico',
    )
    status = forms.ChoiceField(
        choices=Enrollment.STATUS,
        initial='active',
        label='Estado de matricula',
    )
    file = forms.FileField(
        label='Archivo Excel (.xlsx)',
        help_text='Usa la plantilla para evitar errores de columnas/formato.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
