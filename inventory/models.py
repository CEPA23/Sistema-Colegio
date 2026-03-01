from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Product(models.Model):
    CATEGORY_BOOK = 'libro'
    CATEGORY_BAND_UNIFORM = 'uniforme_banda'
    CATEGORY_SCHOOL_UNIFORM = 'uniforme_colegio'
    CATEGORY_OTHER = 'otro'

    CATEGORY_CHOICES = (
        (CATEGORY_BOOK, 'Libro'),
        (CATEGORY_BAND_UNIFORM, 'Uniforme de Banda'),
        (CATEGORY_SCHOOL_UNIFORM, 'Uniforme del Colegio'),
        (CATEGORY_OTHER, 'Otro'),
    )

    code = models.CharField(max_length=30, unique=True, verbose_name='ID/Código')
    name = models.CharField(max_length=120, verbose_name='Producto')
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default=CATEGORY_OTHER, verbose_name='Categoría')
    description = models.TextField(blank=True, verbose_name='Descripción')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Precio (S/)')
    stock = models.PositiveIntegerField(default=0, verbose_name='Stock actual')
    stock_min = models.PositiveIntegerField(default=5, verbose_name='Stock mínimo')
    stock_max = models.PositiveIntegerField(default=100, verbose_name='Stock máximo')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('category', 'name')
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    def __str__(self):
        return f'[{self.code}] {self.name}'

    @property
    def is_low_stock(self):
        return self.stock <= self.stock_min

    @property
    def stock_status(self):
        if self.stock == 0:
            return 'agotado'
        if self.stock <= self.stock_min:
            return 'minimo'
        if self.stock >= self.stock_max:
            return 'maximo'
        return 'normal'

    def clean(self):
        super().clean()
        if self.price <= Decimal('0.00'):
            raise ValidationError({'price': 'El precio debe ser mayor a cero.'})
        if self.stock_min >= self.stock_max:
            raise ValidationError({'stock_min': 'El stock mínimo debe ser menor que el stock máximo.'})


class StockMovement(models.Model):
    TYPE_IN = 'entrada'
    TYPE_OUT = 'salida'
    TYPE_ADJUSTMENT = 'ajuste'

    TYPE_CHOICES = (
        (TYPE_IN, 'Entrada'),
        (TYPE_OUT, 'Salida (venta)'),
        (TYPE_ADJUSTMENT, 'Ajuste'),
    )

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements', verbose_name='Producto')
    movement_type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name='Tipo')
    quantity = models.PositiveIntegerField(verbose_name='Cantidad')
    previous_stock = models.PositiveIntegerField(verbose_name='Stock anterior')
    new_stock = models.PositiveIntegerField(verbose_name='Stock nuevo')
    reference = models.CharField(max_length=120, blank=True, verbose_name='Referencia/Motivo')
    # Optional link to finance payment
    payment = models.ForeignKey(
        'finance.Payment',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='stock_movements',
        verbose_name='Pago relacionado'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Registrado por'
    )

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Movimiento de Stock'
        verbose_name_plural = 'Movimientos de Stock'

    def __str__(self):
        return f'{self.get_movement_type_display()} {self.quantity} x {self.product} ({self.created_at:%d/%m/%Y})'
