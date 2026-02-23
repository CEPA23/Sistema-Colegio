from django.urls import path

from .views import (
    academic_dashboard,
    course_report,
    course_management,
    grade_management,
    section_management,
    delete_competency,
    delete_indicator,
    grade_create,
    grade_list,
    manage_competencies,
    manage_indicators,
    period_report,
    report_card,
    student_report,
    student_report_pdf,
    teacher_competency_gradebook,
    auto_assign_poly_courses,
)


urlpatterns = [
    path('dashboard/', academic_dashboard, name='academic_dashboard'),
    path('courses/', course_management, name='course_management'),
    path('grades-config/', grade_management, name='grade_management'),
    path('sections/', section_management, name='section_management'),
    path('courses/<int:course_id>/competencies/', manage_competencies, name='manage_competencies'),
    path('competencies/delete/<int:competency_id>/', delete_competency, name='delete_competency'),
    path('competencies/<int:competency_id>/indicators/', manage_indicators, name='manage_indicators'),
    path('indicators/delete/<int:indicator_id>/', delete_indicator, name='delete_indicator'),
    path('', grade_list, name='grade_list'),
    path('new/', grade_create, name='grade_create'),
    path('report/', report_card, name='report_card'),
    path('report/<int:enrollment_id>/', student_report, name='student_report'),
    path('report/<int:enrollment_id>/pdf/', student_report_pdf, name='student_report_pdf'),
    path('report-course/', course_report, name='course_report'),
    path('report-period/', period_report, name='period_report'),
    path('teacher/competencies/', teacher_competency_gradebook, name='teacher_competency_gradebook'),
    path('courses/auto-assign-poly/', auto_assign_poly_courses, name='auto_assign_poly_courses'),
]
