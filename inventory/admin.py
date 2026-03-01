from django.contrib import admin
from .models import Product, StockMovement


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'price', 'stock', 'stock_min', 'stock_max', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('category', 'name')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('product', 'movement_type', 'quantity', 'previous_stock', 'new_stock', 'reference', 'created_at', 'created_by')
    list_filter = ('movement_type',)
    search_fields = ('product__name', 'product__code', 'reference')
    readonly_fields = ('previous_stock', 'new_stock', 'created_at')
