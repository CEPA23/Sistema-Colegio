from django.urls import path

from .views import (
    academic_dashboard,
    course_management,
    course_report,
    grade_create,
    grade_list,
    period_report,
    report_card,
    student_report,
    student_report_pdf,
    teacher_competency_gradebook,
)


urlpatterns = [
    path('dashboard/', academic_dashboard, name='academic_dashboard'),
    path('courses/manage/', course_management, name='course_management'),
    path('', grade_list, name='grade_list'),
    path('new/', grade_create, name='grade_create'),
    path('report/', report_card, name='report_card'),
    path('report/<int:enrollment_id>/', student_report, name='student_report'),
    path('report/<int:enrollment_id>/pdf/', student_report_pdf, name='student_report_pdf'),
    path('report-course/', course_report, name='course_report'),
    path('report-period/', period_report, name='period_report'),
    path('teacher/competencies/', teacher_competency_gradebook, name='teacher_competency_gradebook'),
]
