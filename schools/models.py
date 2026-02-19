from django.db import models

class School(models.Model):
    name = models.CharField(max_length=255)
    logo = models.FileField(upload_to='school_logos/', blank=True, null=True)
    address = models.TextField()
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    ruc = models.CharField(max_length=11, blank=True, null=True, verbose_name="RUC")
    
    # Configuracion de Negocio
    pension_price = models.DecimalField(max_digits=10, decimal_places=2, default=200.00, verbose_name="Costo de Pension")
    enrollment_price = models.DecimalField(max_digits=10, decimal_places=2, default=300.00, verbose_name="Costo de Matricula")
    supplies_price = models.DecimalField(max_digits=10, decimal_places=2, default=50.00, verbose_name="Costo de Material Escolar")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
