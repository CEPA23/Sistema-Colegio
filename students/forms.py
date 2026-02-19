from django import forms

from academic.models import AcademicYear, Section
from enrollment.models import Enrollment

from .models import Student


class StudentEnrollmentForm(forms.ModelForm):
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.none(),
        label='Anio academico'
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.none(),
        label='Seccion (grado)'
    )
    enrollment_status = forms.ChoiceField(
        choices=Enrollment.STATUS,
        initial='active',
        label='Estado de matricula'
    )

    class Meta:
        model = Student
        fields = [
            'dni',
            'first_name',
            'last_name',
            'birth_date',
            'address',
            'parent_name',
            'parent_phone',
            'academic_year',
            'section',
            'enrollment_status',
        ]
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['academic_year'].queryset = AcademicYear.objects.select_related('school').order_by('-year')
        self.fields['section'].queryset = Section.objects.select_related('grade').order_by('grade__name', 'name')
        self.fields['section'].label_from_instance = lambda s: f"{s.grade} - {s.name}"
