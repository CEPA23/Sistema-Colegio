from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from enrollment.models import Enrollment


class Fee(models.Model):
    CONCEPT_ENROLLMENT = 'matricula'
    CONCEPT_PENSION = 'pension'
    CONCEPT_SCHOOL_SUPPLIES = 'material_escolar'
    CONCEPT_BOOK = 'libro'
    CONCEPT_CHOICES = (
        (CONCEPT_ENROLLMENT, 'Matricula'),
        (CONCEPT_PENSION, 'Pension'),
        (CONCEPT_SCHOOL_SUPPLIES, 'Material escolar'),
        (CONCEPT_BOOK, 'Libro'),
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
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()

    STATUS = (
        ('pending', 'Pendiente'),
        ('paid', 'Pagado'),
        ('late', 'Vencido'),
    )

    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.concept == self.CONCEPT_PENSION and self.pension_month:
            return f"{self.get_concept_display()} ({self.get_pension_month_display()}) - {self.enrollment}"
        return f"{self.get_concept_display()} - {self.enrollment}"

    @property
    def total_paid(self):
        total = self.payment_set.aggregate(total=Sum('amount'))['total']
        return total or Decimal('0.00')

    @property
    def balance(self):
        remaining = self.amount - self.total_paid
        return remaining if remaining > Decimal('0.00') else Decimal('0.00')

    def refresh_status(self):
        if self.balance <= Decimal('0.00'):
            self.status = 'paid'
        elif self.due_date < timezone.localdate():
            self.status = 'late'
        else:
            self.status = 'pending'
        self.save(update_fields=['status'])


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

        remaining = self.fee.balance
        if self.pk:
            previous = Payment.objects.get(pk=self.pk).amount
            remaining += previous

        if self.amount > remaining:
            raise ValidationError("El monto excede la deuda pendiente.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.fee.refresh_status()
