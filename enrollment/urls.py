from django.urls import path

from .views import (
    enrollment_create,
    enrollment_dashboard,
    enrollment_detail,
    enrollment_edit,
    enrollment_history,
    enrollment_import_students,
    enrollment_import_template,
    enrollment_list,
    enrollment_renew,
)

urlpatterns = [
    path('dashboard/', enrollment_dashboard, name='enrollment_dashboard'),
    path('', enrollment_list, name='enrollment_list'),
    path('new/', enrollment_create, name='enrollment_create'),
    path('import/students/', enrollment_import_students, name='enrollment_import_students'),
    path('import/students/template/', enrollment_import_template, name='enrollment_import_template'),
    path('<int:enrollment_id>/', enrollment_detail, name='enrollment_detail'),
    path('<int:enrollment_id>/edit/', enrollment_edit, name='enrollment_edit'),
    path('<int:enrollment_id>/renew/', enrollment_renew, name='enrollment_renew'),
    path('history/student/<int:student_id>/', enrollment_history, name='enrollment_history'),
]
