from django.urls import path

from .views import (
    attendance_course_report,
    attendance_dashboard,
    attendance_export_csv,
    attendance_student_history,
    attendance_take,
)


urlpatterns = [
    path('dashboard/', attendance_dashboard, name='attendance_dashboard'),
    path('take/', attendance_take, name='attendance_take'),
    path('student/<int:enrollment_id>/', attendance_student_history, name='attendance_student_history'),
    path('report-course/', attendance_course_report, name='attendance_course_report'),
    path('export/', attendance_export_csv, name='attendance_export_csv'),
]
