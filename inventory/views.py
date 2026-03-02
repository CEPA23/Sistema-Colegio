from django.contrib import messages
from django.db import transaction
from django.db.models import Q, F
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse, HttpResponse, FileResponse

from accounts.decorators import role_required
from .forms import ProductForm, StockAdjustmentForm, SaleForm
from .models import Product, StockMovement


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def get_low_stock_products_qs():
    """Returns the queryset of active products that are at or below minimum stock."""
    return Product.objects.filter(is_active=True, stock__lte=F('stock_min'))


def _discount_stock(product, quantity, reference='', payment=None, user=None):
    """Reduce stock and create a movement record. Raises ValueError if not enough stock."""
    if product.stock < quantity:
        raise ValueError(f'Stock insuficiente. Disponible: {product.stock}')
    previous = product.stock
    product.stock -= quantity
    product.save(update_fields=['stock'])
    StockMovement.objects.create(
        product=product,
        movement_type=StockMovement.TYPE_OUT,
        quantity=quantity,
        previous_stock=previous,
        new_stock=product.stock,
        reference=reference,
        payment=payment,
        created_by=user,
    )
    return product


def _increase_stock(product, quantity, movement_type=StockMovement.TYPE_IN, reference='', user=None):
    previous = product.stock
    product.stock += quantity
    product.save(update_fields=['stock'])
    StockMovement.objects.create(
        product=product,
        movement_type=movement_type,
        quantity=quantity,
        previous_stock=previous,
        new_stock=product.stock,
        reference=reference,
        created_by=user,
    )
    return product


# ──────────────────────────────────────────────
# Inventory dashboard / product list
# ──────────────────────────────────────────────

@role_required('admin', 'director', 'secretary', 'teacher')
def inventory_list(request):
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()

    products = Product.objects.all()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(code__icontains=query))
    if category:
        products = products.filter(category=category)

    # Use the helper for consistency
    low_stock = get_low_stock_products_qs()
    out_of_stock = products.filter(stock=0)

    context = {
        'products': products,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'low_stock_count': low_stock.count(),
        'query': query,
        'category': category,
        'category_choices': Product.CATEGORY_CHOICES,
    }
    return render(request, 'inventory/inventory_list.html', context)


# ──────────────────────────────────────────────
# Product CRUD
# ──────────────────────────────────────────────

@role_required('admin', 'director')
def product_create(request):
    form = ProductForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        product = form.save()
        if product.stock > 0:
            StockMovement.objects.create(
                product=product,
                movement_type=StockMovement.TYPE_IN,
                quantity=product.stock,
                previous_stock=0,
                new_stock=product.stock,
                reference='Stock inicial',
                created_by=request.user,
            )
        messages.success(request, f'Producto "{product.name}" creado correctamente.')
        return redirect('inventory_list')
    return render(request, 'inventory/product_form.html', {'form': form, 'title': 'Nuevo Producto'})


@role_required('admin', 'director')
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    old_stock = product.stock
    form = ProductForm(request.POST or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        product = form.save()
        new_stock = product.stock
        if new_stock != old_stock:
            diff = new_stock - old_stock
            StockMovement.objects.create(
                product=product,
                movement_type=StockMovement.TYPE_ADJUSTMENT,
                quantity=abs(diff),
                previous_stock=old_stock,
                new_stock=new_stock,
                reference='Edición de producto',
                created_by=request.user,
            )
        messages.success(request, f'Producto "{product.name}" actualizado.')
        return redirect('inventory_list')
    return render(request, 'inventory/product_form.html', {'form': form, 'title': 'Editar Producto', 'product': product})


@role_required('admin', 'director')
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        name = product.name
        product.is_active = False
        product.save(update_fields=['is_active'])
        messages.success(request, f'Producto "{name}" desactivado.')
        return redirect('inventory_list')
    return render(request, 'inventory/product_confirm_delete.html', {'product': product})


# ──────────────────────────────────────────────
# Stock adjustments
# ──────────────────────────────────────────────

@role_required('admin', 'director', 'secretary')
def stock_adjust(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = StockAdjustmentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        qty = form.cleaned_data['quantity']
        mv_type = form.cleaned_data['movement_type']
        ref = form.cleaned_data.get('reference', '')
        previous = product.stock
        with transaction.atomic():
            product.stock += qty
            product.save(update_fields=['stock'])
            StockMovement.objects.create(
                product=product,
                movement_type=mv_type,
                quantity=qty,
                previous_stock=previous,
                new_stock=product.stock,
                reference=ref,
                created_by=request.user,
            )
        messages.success(request, f'Stock de "{product.name}" actualizado a {product.stock} unidades.')
        return redirect('inventory_list')
    return render(request, 'inventory/stock_adjust.html', {'form': form, 'product': product})


# ──────────────────────────────────────────────
# Quick Sale
# ──────────────────────────────────────────────

@role_required('admin', 'director', 'secretary')
def inventory_sale(request):
    form = SaleForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        product = form.cleaned_data['product']
        qty = form.cleaned_data['quantity']
        ref = form.cleaned_data.get('reference', '')
        try:
            with transaction.atomic():
                _discount_stock(product, qty, reference=ref or 'Venta directa', user=request.user)
            messages.success(request, f'Venta registrada: {qty} x "{product.name}".')
        except ValueError as exc:
            form.add_error('quantity', str(exc))
            return render(request, 'inventory/inventory_sale.html', {'form': form})
        return redirect('inventory_list')
    return render(request, 'inventory/inventory_sale.html', {'form': form})


# ──────────────────────────────────────────────
# History
# ──────────────────────────────────────────────

@role_required('admin', 'director', 'secretary')
def movement_history(request, pk=None):
    if pk:
        product = get_object_or_404(Product, pk=pk)
        movements = StockMovement.objects.filter(product=product).select_related('product', 'created_by').order_by('-created_at')
        title = f'Movimientos: {product.name}'
    else:
        product = None
        movements = StockMovement.objects.select_related('product', 'created_by').order_by('-created_at')[:200]
        title = 'Historial de Movimientos'
    return render(request, 'inventory/movement_history.html', {'movements': movements, 'product': product, 'title': title})


# ──────────────────────────────────────────────
# APIs & Exports
# ──────────────────────────────────────────────

@role_required('admin', 'director', 'secretary')
def low_stock_alert_api(request):
    low = get_low_stock_products_qs().values('id', 'code', 'name', 'stock', 'stock_min')
    return JsonResponse({'count': low.count(), 'products': list(low)})


@role_required('admin', 'director', 'secretary')
def inventory_export_csv(request):
    import csv
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventario_escolar.csv"'
    writer = csv.writer(response)
    writer.writerow(['Código', 'Producto', 'Categoría', 'Precio', 'Stock', 'Mínimo', 'Estado'])
    for p in Product.objects.filter(is_active=True):
        writer.writerow([p.code, p.name, p.get_category_display(), p.price, p.stock, p.stock_min, p.stock_status.upper()])
    return response


@role_required('admin', 'director', 'secretary')
def product_barcode_download(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not product.barcode:
        messages.error(request, "Sin código de barras.")
        return redirect('inventory_list')
    return FileResponse(product.barcode.open(), content_type='image/png', as_attachment=True, filename=f"barcode_{product.code}.png")
