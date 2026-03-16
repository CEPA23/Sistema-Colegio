from django.urls import path
from .views import student_create, student_delete, student_edit, student_list, student_profile

urlpatterns = [
    path('', student_list, name='student_list'),
    path('new/', student_create, name='student_create'),
    path('<int:student_id>/', student_profile, name='student_profile'),
    path('<int:student_id>/edit/', student_edit, name='student_edit'),
    path('<int:student_id>/delete/', student_delete, name='student_delete'),
]
