from django.contrib import admin
from .models import Fee, Payment


@admin.register(Fee)
class FeeAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'concept', 'pension_month', 'course', 'amount', 'amount_paid', 'status', 'due_date')
    list_filter = ('concept', 'status', 'pension_month', 'enrollment__section__grade')
    search_fields = ('enrollment__student__first_name', 'enrollment__student__last_name', 'enrollment__student__dni')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_date', 'fee', 'amount', 'method')
    list_filter = ('method', 'payment_date')
    search_fields = ('fee__enrollment__student__first_name', 'fee__enrollment__student__last_name')
