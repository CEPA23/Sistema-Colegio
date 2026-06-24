from django import forms

from academic.models import Section
from core.teacher_access import teacher_section_ids

from .models import AttendanceRecord


class AttendanceRecordForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ['enrollment', 'date', 'status', 'note']


class AttendanceSheetFilterForm(forms.Form):
    date = forms.DateField(
        label='Fecha',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    section = forms.ModelChoiceField(
        label='Grado / Seccion',
        queryset=Section.objects.none(),
        empty_label='Selecciona grado y seccion',
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        sections = Section.objects.select_related('grade').order_by('grade__name', 'name')
        if user and user.role == 'teacher' and not user.is_superuser:
            section_ids = teacher_section_ids(user)
            if section_ids:
                sections = sections.filter(id__in=section_ids)
            else:
                sections = sections.none()
        self.fields['section'].queryset = sections
