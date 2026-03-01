from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from enrollment.models import Enrollment


class Fee(models.Model):
    CONCEPT_ENROLLMENT = 'matricula'
    CONCEPT_PENSION = 'pension'
    CONCEPT_SCHOOL_SUPPLIES = 'material_escolar'
    CONCEPT_BOOK = 'libro'
    CONCEPT_BAND_UNIFORM = 'uniforme_banda'
    CONCEPT_SCHOOL_UNIFORM = 'uniforme_colegio'
    CONCEPT_PRODUCT = 'producto_inventario'
    CONCEPT_CHOICES = (
        (CONCEPT_ENROLLMENT, 'Matricula'),
        (CONCEPT_PENSION, 'Pension'),
        (CONCEPT_SCHOOL_SUPPLIES, 'Material escolar'),
        (CONCEPT_BOOK, 'Libro'),
        (CONCEPT_BAND_UNIFORM, 'Uniforme de Banda'),
        (CONCEPT_SCHOOL_UNIFORM, 'Uniforme del Colegio'),
        (CONCEPT_PRODUCT, 'Producto de inventario'),
    )

    MONTH_CHOICES = (
        (1, 'Enero'),
        (2, 'Febrero'),
        (3, 'Marzo'),
        (4, 'Abril'),
        (5, 'Mayo'),
        (6, 'Junio'),
        (7, 'Julio'),
        (8, 'Agosto'),
        (9, 'Setiembre'),
        (10, 'Octubre'),
        (11, 'Noviembre'),
        (12, 'Diciembre'),
    )

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE)
    concept = models.CharField(max_length=30, choices=CONCEPT_CHOICES)
    pension_month = models.PositiveSmallIntegerField(choices=MONTH_CHOICES, null=True, blank=True)
    course = models.ForeignKey('academic.Course', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Curso (para libros)")
    inventory_product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Producto de inventario',
        related_name='fees',
    )
    inventory_quantity = models.PositiveIntegerField(default=1, verbose_name='Cantidad vendida')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    due_date = models.DateField()

    STATUS = (
        ('pending', 'Pendiente'),
        ('partial', 'Parcial'),
        ('paid', 'Pagado'),
    )

    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.concept == self.CONCEPT_PENSION and self.pension_month:
            return f"{self.get_concept_display()} ({self.get_pension_month_display()}) - {self.enrollment}"
        return f"{self.get_concept_display()} - {self.enrollment}"

    @property
    def total_paid(self):
        return self.amount_paid or Decimal('0.00')

    @property
    def balance(self):
        remaining = self.amount - self.total_paid
        return remaining if remaining > Decimal('0.00') else Decimal('0.00')

    @property
    def pending(self):
        return self.balance

    def refresh_status(self, save=True):
        if self.pending <= Decimal('0.00'):
            self.status = 'paid'
        elif self.total_paid > Decimal('0.00'):
            self.status = 'partial'
        else:
            self.status = 'pending'
        if save:
            self.save(update_fields=['status'])

    def recalculate_from_payments(self):
        total = self.payment_set.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        if total > self.amount:
            total = self.amount
        self.amount_paid = total
        self.refresh_status(save=False)
        self.save(update_fields=['amount_paid', 'status'])

    def clean(self):
        super().clean()
        if self.amount <= Decimal('0.00'):
            raise ValidationError({'amount': "El monto total de la deuda debe ser mayor a cero."})
        if self.amount_paid < Decimal('0.00'):
            raise ValidationError({'amount_paid': "El monto pagado no puede ser negativo."})
        if self.amount_paid > self.amount:
            raise ValidationError({'amount_paid': "El monto pagado no puede exceder el monto total."})

        if self.concept == self.CONCEPT_PENSION:
            if not self.pension_month:
                raise ValidationError({'pension_month': "La pension requiere mes."})
            if self.course_id:
                raise ValidationError({'course': "La pension no debe tener curso asociado."})
        elif self.concept == self.CONCEPT_BOOK:
            if not self.course_id:
                raise ValidationError({'course': "El concepto libro requiere curso."})
            if self.pension_month:
                raise ValidationError({'pension_month': "El concepto libro no debe tener mes."})
        else:
            if self.pension_month:
                raise ValidationError({'pension_month': "Este concepto no debe tener mes."})
            if self.course_id:
                raise ValidationError({'course': "Este concepto no debe tener curso."})


class Payment(models.Model):
    METHOD_CASH = 'cash'
    METHOD_TRANSFER = 'transfer'
    METHOD_YAPE_PLIN = 'yape_plin'
    METHOD_CHOICES = (
        (METHOD_CASH, 'Efectivo'),
        (METHOD_TRANSFER, 'Transferencia'),
        (METHOD_YAPE_PLIN, 'Yape/Plin'),
    )

    fee = models.ForeignKey(Fee, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(auto_now_add=True)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=METHOD_CASH)
    proof_image = models.FileField(upload_to='payment_proofs/', blank=True, null=True)
    comment = models.TextField(blank=True)

    def __str__(self):
        return f"Pago {self.amount} - {self.fee}"

    def clean(self):
        if self.amount <= Decimal('0.00'):
            raise ValidationError("El monto del pago debe ser mayor a cero.")

        if self.method in (self.METHOD_TRANSFER, self.METHOD_YAPE_PLIN) and not self.proof_image:
            raise ValidationError("Debes adjuntar una captura para transferencias o Yape/Plin.")

        aggregate = Payment.objects.filter(fee=self.fee).exclude(pk=self.pk).aggregate(total=Sum('amount'))
        already_paid_without_current = aggregate['total'] or Decimal('0.00')
        remaining = self.fee.amount - already_paid_without_current

        if self.amount > remaining:
            raise ValidationError("El monto excede la deuda pendiente.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.fee.recalculate_from_payments()

    def delete(self, *args, **kwargs):
        fee = self.fee
        super().delete(*args, **kwargs)
        fee.recalculate_from_payments()
