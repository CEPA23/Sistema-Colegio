from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from collections import Counter
from schools.models import School


class AcademicYear(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    year = models.IntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.school.name} - {self.year}"


class Grade(models.Model):
    name = models.CharField(max_length=50)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class Section(models.Model):
    name = models.CharField(max_length=10)
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE)
    tutor_teacher = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='tutor_sections',
        limit_choices_to={'role': 'teacher'},
        verbose_name='Tutora de aula',
    )

    class Meta:
        ordering = ('grade__name', 'name')
        unique_together = ('grade', 'name')

    def __str__(self):
        return f"{self.grade} - {self.name}"


class Course(models.Model):
    name = models.CharField(max_length=100)
    is_poly_course = models.BooleanField(default=False, verbose_name="¿Es curso de polidocencia?")

    def __str__(self):
        return self.name


class TeacherCourseAssignment(models.Model):
    teacher = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'}
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    grade = models.ForeignKey(Grade, on_delete=models.SET_NULL, null=True, blank=True)
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('teacher', 'course', 'section', 'academic_year')
        ordering = ('academic_year__year', 'grade__name', 'section__name', 'course__name')

    def __str__(self):
        grade_name = self.grade.name if self.grade else '-'
        section_name = self.section.name if self.section else '-'
        return (
            f"{self.course.name} | {grade_name} {section_name} "
            f"({self.academic_year.year}) - {self.teacher}"
        )

    def clean(self):
        if self.section:
            section_grade = self.section.grade
            if self.grade and self.grade_id != section_grade.id:
                raise ValidationError({'grade': 'El grado debe coincidir con la seccion seleccionada.'})
            self.grade = section_grade

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Period(models.Model):
    name = models.CharField(max_length=50)  # Ej: Bimestre 1
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ('-academic_year__year', 'start_date', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=['is_active'],
                condition=Q(is_active=True),
                name='unique_active_period',
            ),
            models.UniqueConstraint(
                fields=['academic_year', 'name'],
                name='unique_period_name_per_year',
            ),
        ]

    def __str__(self):
        return f"{self.name} - {self.academic_year}"

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({'end_date': 'La fecha de fin debe ser mayor o igual a la fecha de inicio.'})


def calculate_final_grade(grades):
    """Calculate a final qualitative grade from multiple period grades."""
    if not grades:
        return None

    weights = {'C': 1, 'B': 2, 'A': 3, 'AD': 4}
    valid_weights = [weights[g] for g in grades if g in weights]

    if not valid_weights:
        return None

    average = sum(valid_weights) / len(valid_weights)
    if average >= 3.5:
        return 'AD'
    if average >= 2.5:
        return 'A'
    if average >= 1.5:
        return 'B'
    return 'C'


def calculate_mode_grade(grades):
    valid = [grade for grade in grades if grade in {'AD', 'A', 'B', 'C'}]
    if not valid:
        return None

    counts = Counter(valid)
    top_frequency = max(counts.values())
    candidates = [grade for grade, frequency in counts.items() if frequency == top_frequency]
    priority = {'C': 1, 'B': 2, 'A': 3, 'AD': 4}
    return max(candidates, key=lambda grade: priority[grade])


class GradeRecord(models.Model):
    enrollment = models.ForeignKey('enrollment.Enrollment', on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    period = models.ForeignKey(Period, on_delete=models.CASCADE)

    GRADE_SCALE = (
        ('AD', 'AD'),
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
    )
    grade = models.CharField(max_length=2, choices=GRADE_SCALE, default='A')

    def __str__(self):
        return f"{self.enrollment} - {self.course} - {self.grade}"

    class Meta:
        unique_together = ('enrollment', 'course', 'period')

    @staticmethod
    def get_final_grade(enrollment, course):
        grades = GradeRecord.objects.filter(
            enrollment=enrollment,
            course=course
        ).values_list('grade', flat=True)
        return calculate_final_grade(list(grades))


class Competency(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ('order', 'id')

    def __str__(self):
        return f"{self.course} - {self.name}"


class Indicator(models.Model):
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ('order', 'id')

    def __str__(self):
        return f"{self.competency.name} - {self.name}"


class IndicatorGrade(models.Model):
    enrollment = models.ForeignKey('enrollment.Enrollment', on_delete=models.CASCADE)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)
    period = models.ForeignKey(Period, on_delete=models.CASCADE)

    GRADE_SCALE = (
        ('AD', 'AD'),
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
    )
    grade = models.CharField(max_length=2, choices=GRADE_SCALE)

    class Meta:
        unique_together = ('enrollment', 'indicator', 'period')

    def __str__(self):
        return f"{self.enrollment} - {self.indicator} - {self.grade}"
