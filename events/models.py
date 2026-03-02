from django.db import models
from django.conf import settings

class Event(models.Model):
    title = models.CharField(max_length=200, verbose_name="Nombre del Evento")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    start_date = models.DateField(verbose_name="Fecha de Inicio")
    end_date = models.DateField(blank=True, null=True, verbose_name="Fecha de Fin")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="Creado por")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"
        ordering = ['start_date']

    def __str__(self):
        return self.title

    @property
    def is_range(self):
        return self.end_date is not None and self.end_date != self.start_date
