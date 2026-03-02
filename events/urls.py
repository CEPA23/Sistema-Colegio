from django.urls import path
from . import views

app_name = 'events'

urlpatterns = [
    path('calendar/', views.event_calendar, name='calendar'),
    path('create/', views.event_create, name='event_create'),
    path('json/', views.event_json, name='event_json'),
]
