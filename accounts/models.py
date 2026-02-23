from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):

    ROLE_CHOICES = (
        ('admin', 'Administrador'),
        ('director', 'Director'),
        ('teacher', 'Docente'),
        ('secretary', 'Secretaria'),
        ('parent', 'Padre'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=15, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True, verbose_name="Foto de Perfil")
    # Eliminar teaching_level
    teaching_grade = models.ForeignKey(
        'academic.Grade',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='teachers',
    )
    teaching_section = models.ForeignKey(
        'academic.Section',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='teachers_by_section',
    )
    is_polyteacher = models.BooleanField(default=False, verbose_name='Es polidocente')
    poly_course = models.ForeignKey(
        'academic.Course',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='poly_teachers_assigned',
        verbose_name='Curso de polidocencia'
    )
    teaching_courses = models.ManyToManyField(
        'academic.Course',
        blank=True,
        related_name='poly_teachers',
        verbose_name='Cursos que enseña (polidocente) - MÚLTIPLES'
    )
    teaching_grades = models.ManyToManyField(
        'academic.Grade',
        blank=True,
        related_name='poly_teachers_grades',
        verbose_name='Grados que enseña (polidocente)'
    )
    teaching_sections = models.ManyToManyField(
        'academic.Section',
        blank=True,
        related_name='poly_teachers_sections',
        verbose_name='Secciones que enseña (polidocente)'
    )

    def __str__(self):
        return self.username

    def clean(self):
        super().clean()
        if self.role == 'teacher':
            if not self.is_polyteacher:
                # Para docentes no polidocentes, validar grado y sección
                if not self.teaching_grade:
                    raise ValidationError({'teaching_grade': 'Debes seleccionar el grado que enseña el docente.'})
                if not self.teaching_section:
                    raise ValidationError({'teaching_section': 'Debes seleccionar la sección que enseña el docente.'})
                if self.teaching_section and self.teaching_section.grade_id != self.teaching_grade_id:
                    raise ValidationError({'teaching_section': 'La sección no pertenece al grado seleccionado.'})
        else:
            # Limpiar campos de docente si no es teacher
            self.teaching_grade = None
            self.teaching_section = None
            self.is_polyteacher = False
            # No limpiar ManyToMany aquí, se hace en el form


class ActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=150)
    path = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    ip_address = models.CharField(max_length=45, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"{self.created_at} - {self.user} - {self.method} {self.path}"
