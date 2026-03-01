from django import forms
from .models import Product, StockMovement


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['code', 'name', 'category', 'description', 'price', 'stock', 'stock_min', 'stock_max', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: LIB-001'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del producto'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Descripción opcional'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'stock_min': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'stock_max': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'code': 'ID / Código',
            'name': 'Nombre del producto',
            'category': 'Categoría',
            'description': 'Descripción',
            'price': 'Precio (S/)',
            'stock': 'Stock actual',
            'stock_min': 'Stock mínimo',
            'stock_max': 'Stock máximo',
            'is_active': '¿Producto activo?',
        }


class StockAdjustmentForm(forms.Form):
    MOVEMENT_CHOICES = (
        ('entrada', 'Entrada de stock'),
        ('ajuste', 'Ajuste manual'),
    )
    movement_type = forms.ChoiceField(choices=MOVEMENT_CHOICES, label='Tipo', widget=forms.Select(attrs={'class': 'form-select'}))
    quantity = forms.IntegerField(min_value=1, label='Cantidad', widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}))
    reference = forms.CharField(max_length=120, required=False, label='Motivo / Referencia',
                                widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Reposición de almacén'}))


class SaleForm(forms.Form):
    """Quick sale from inventory without linking to a student fee."""
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True, stock__gt=0),
        label='Producto',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    quantity = forms.IntegerField(min_value=1, label='Cantidad', widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}))
    reference = forms.CharField(max_length=120, required=False, label='Referencia / Cliente',
                                widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre o nota'}))
