from django import forms

from accounts.models import User

from .models import Course, Grade, GradeRecord, Level, Section, TeacherCourseAssignment


class GradeRecordForm(forms.ModelForm):
    class Meta:
        model = GradeRecord
        fields = ['enrollment', 'course', 'period', 'grade']


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['name']


class TeacherCourseAssignmentForm(forms.ModelForm):
    class Meta:
        model = TeacherCourseAssignment
        fields = ['academic_year', 'level', 'grade', 'section', 'course', 'teacher']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teacher'].queryset = User.objects.filter(role='teacher').order_by('first_name', 'last_name')
        self.fields['level'].queryset = Level.objects.order_by('name')
        self.fields['grade'].queryset = Grade.objects.order_by('name')
        self.fields['section'].queryset = Section.objects.select_related('grade').order_by('grade__name', 'name')

        level = None
        if self.is_bound:
            level = self.data.get('level')
        elif self.instance.pk and self.instance.level_id:
            level = str(self.instance.level_id)
        if level:
            self.fields['grade'].queryset = Grade.objects.filter(level_id=level).order_by('name')

        grade = None
        if self.is_bound:
            grade = self.data.get('grade')
        elif self.instance.pk and self.instance.grade_id:
            grade = str(self.instance.grade_id)
        if grade:
            self.fields['section'].queryset = Section.objects.filter(grade_id=grade).order_by('name')
