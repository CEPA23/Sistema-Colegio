from django.urls import path
from .views import student_create, student_list, student_profile

urlpatterns = [
    path('', student_list, name='student_list'),
    path('new/', student_create, name='student_create'),
    path('<int:student_id>/', student_profile, name='student_profile'),
]
