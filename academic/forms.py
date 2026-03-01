from django import forms

from accounts.models import User

from .models import Competency, Course, Grade, GradeRecord, Indicator, Section, TeacherCourseAssignment


class GradeRecordForm(forms.ModelForm):
    class Meta:
        model = GradeRecord
        fields = ['enrollment', 'course', 'period', 'grade']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.role == 'teacher' and not user.is_superuser:
            # Filter courses
            assigned_course_ids = TeacherCourseAssignment.objects.filter(
                teacher=user
            ).values_list('course_id', flat=True)
            self.fields['course'].queryset = Course.objects.filter(id__in=assigned_course_ids)

            # Filter enrollments (find relevant sections first)
            from django.db.models import Q
            assignments = TeacherCourseAssignment.objects.filter(teacher=user)
            q_sections = Q(id__in=[])
            for a in assignments:
                if a.section_id:
                    q_sections |= Q(id=a.section_id)
                elif a.grade_id:
                    q_sections |= Q(grade_id=a.grade_id)
            
            from enrollment.models import Enrollment
            relevant_section_ids = Section.objects.filter(q_sections).values_list('id', flat=True)
            self.fields['enrollment'].queryset = Enrollment.objects.filter(
                section_id__in=relevant_section_ids,
                status='active'
            ).select_related('student')


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['name', 'is_poly_course']


class GradeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = ['name']


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ['name', 'grade', 'tutor_teacher']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tutor_teacher'].queryset = User.objects.filter(role='teacher').order_by('first_name', 'last_name')


class TeacherCourseAssignmentForm(forms.ModelForm):
    class Meta:
        model = TeacherCourseAssignment
        fields = ['academic_year', 'grade', 'section', 'course', 'teacher']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teacher'].queryset = User.objects.filter(role='teacher').order_by('first_name', 'last_name')
        self.fields['grade'].queryset = Grade.objects.order_by('name')
        self.fields['section'].queryset = Section.objects.select_related('grade').order_by('grade__name', 'name')

        grade = None
        if self.is_bound:
            grade = self.data.get('grade')
        elif self.instance.pk and self.instance.grade_id:
            grade = str(self.instance.grade_id)
        if grade:
            self.fields['section'].queryset = Section.objects.filter(grade_id=grade).order_by('name')


class CompetencyForm(forms.ModelForm):
    class Meta:
        model = Competency
        fields = ['name', 'order']


class IndicatorForm(forms.ModelForm):
    class Meta:
        model = Indicator
        fields = ['name', 'order']
