from django.urls import path

from .views import (
    account_status,
    cash_report,
    debtors_export_csv,
    debtors_report,
    debtors_student_search,
    finance_dashboard,
    monthly_report,
    payment_create,
    payment_history,
    payment_receipt_pdf,
    quick_enrollment_create,
    secretary_dashboard,
    student_search,
)


urlpatterns = [
    path('dashboard/', finance_dashboard, name='finance_dashboard'),
    path('secretary/', secretary_dashboard, name='secretary_dashboard'),
    path('pay/', payment_create, name='payment_create'),
    path('students/search/', student_search, name='payment_student_search'),
    path('debtors/students/search/', debtors_student_search, name='debtors_student_search'),
    path('enrollment/quick-create/', quick_enrollment_create, name='payment_quick_enrollment_create'),
    path('account-status/', account_status, name='account_status'),
    path('history/', payment_history, name='payment_history'),
    path('receipt/<int:payment_id>/', payment_receipt_pdf, name='payment_receipt_pdf'),
    path('debtors/', debtors_report, name='debtors_report'),
    path('debtors/export/', debtors_export_csv, name='debtors_export_csv'),
    path('monthly/', monthly_report, name='monthly_report'),
    path('cash/', cash_report, name='cash_report'),
]
