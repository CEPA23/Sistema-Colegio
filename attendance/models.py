from django.conf import settings
from django.core.exceptions import ValidationError
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
        unique_together = ('enrollment', 'date')
        ordering = ('-date', 'enrollment__section__grade__name', 'enrollment__section__name', 'enrollment__student__last_name')

    def __str__(self):
        return f"{self.enrollment} - {self.date} - {self.status}"

    def clean(self):
        super().clean()
        if not self.enrollment_id or not self.date:
            return

        if not self.recorded_by_id and not self.pk:
            raise ValidationError(
                "Debe indicar el docente que registro la asistencia."
            )

        section_id = self.enrollment.section_id
        if not section_id:
            return

        existing = AttendanceRecord.objects.filter(
            enrollment__section_id=section_id,
            date=self.date,
        )
        if self.pk:
            existing = existing.exclude(pk=self.pk)
        owner_record = existing.exclude(recorded_by__isnull=True).first()

        if owner_record and owner_record.recorded_by_id != self.recorded_by_id:
            raise ValidationError(
                "La asistencia de esta seccion y fecha ya fue registrada por otro docente."
            )

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
