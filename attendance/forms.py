from django import forms

from academic.models import TeacherCourseAssignment

from .models import AttendanceRecord


class AttendanceRecordForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ['enrollment', 'assignment', 'date', 'status', 'note']


class AttendanceSheetFilterForm(forms.Form):
    date = forms.DateField(label='Fecha')
    assignment = forms.ModelChoiceField(
        label='Curso',
        queryset=TeacherCourseAssignment.objects.none(),
        empty_label='Selecciona curso',
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        assignments = TeacherCourseAssignment.objects.select_related(
            'teacher',
            'course',
            'section__grade',
            'academic_year',
        ).order_by(
            '-academic_year__year',
            'level__name',
            'grade__name',
            'section__name',
            'course__name',
        )
        if user and user.role == 'teacher' and not user.is_superuser:
            assignments = assignments.filter(teacher=user)
        self.fields['assignment'].queryset = assignments
