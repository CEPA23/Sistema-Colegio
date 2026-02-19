from django.db import models
from students.models import Student
from academic.models import AcademicYear, Section

class Enrollment(models.Model):

    STATUS = (
        ('active', 'Activo'),
        ('retired', 'Retirado'),
        ('transferred', 'Trasladado'),
        ('finished', 'Finalizado'),
    )

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)

    status = models.CharField(max_length=20, choices=STATUS, default='active')
    enrolled_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student} - {self.academic_year}"
