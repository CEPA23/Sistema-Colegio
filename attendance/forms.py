from django import forms

from academic.models import Section, TeacherCourseAssignment

from .models import AttendanceRecord


class AttendanceRecordForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ['enrollment', 'date', 'status', 'note']


class AttendanceSheetFilterForm(forms.Form):
    date = forms.DateField(label='Fecha')
    section = forms.ModelChoiceField(
        label='Seccion',
        queryset=Section.objects.none(),
        empty_label='Selecciona seccion',
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        sections = Section.objects.select_related('grade').order_by('grade__name', 'name')
        if user and user.role == 'teacher' and not user.is_superuser:
            assignment_section_ids = TeacherCourseAssignment.objects.select_related(
                'teacher',
                'course',
                'section__grade',
                'academic_year',
            ).filter(
                teacher=user,
                section__isnull=False,
            ).values_list('section_id', flat=True).distinct()
            tutor_section_ids = Section.objects.filter(
                tutor_teacher=user,
            ).values_list('id', flat=True)
            profile_section_ids = []
            if user.teaching_section_id:
                profile_section_ids.append(user.teaching_section_id)
            profile_section_ids.extend(user.teaching_sections.values_list('id', flat=True))
            section_ids = set(assignment_section_ids).union(tutor_section_ids, profile_section_ids)
            if section_ids:
                sections = sections.filter(id__in=section_ids)
            else:
                sections = sections.none()
        self.fields['section'].queryset = sections
