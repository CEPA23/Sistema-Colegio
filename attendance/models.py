from django.conf import settings
from django.db import models

from enrollment.models import Enrollment


class AttendanceRecord(models.Model):
    STATUS = (
        ('present', 'Asistio'),
        ('absent', 'Falto'),
        ('justified', 'Justificado'),
    )

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE)
    assignment = models.ForeignKey(
        'academic.TeacherCourseAssignment',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='attendance_records',
    )
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default='present')
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('enrollment', 'date', 'assignment')
        ordering = ('-date', 'assignment__course__name', 'enrollment__student__last_name')

    def __str__(self):
        return f"{self.enrollment} - {self.date} - {self.status}"

    @property
    def status_icon(self):
        return {
            'present': '✔',
            'absent': '❌',
            'justified': '✔',
        }.get(self.status, '-')

    @property
    def status_css_class(self):
        return {
            'present': 'attendance-present',
            'absent': 'attendance-absent',
            'justified': 'attendance-justified',
        }.get(self.status, '')
