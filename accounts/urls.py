from django.contrib.auth import views as auth_views
from django.urls import path

from .views import (
    activity_logs,
    dashboard,
    RoleLoginView,
    roles_permissions,
    system_config,
    teacher_dashboard,
    user_delete,
    user_management,
    user_profile,
)


urlpatterns = [
    path('', dashboard, name='dashboard'),
    path(
        'login/',
        RoleLoginView.as_view(),
        name='login'
    ),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
    path('teacher/', teacher_dashboard, name='teacher_dashboard'),
    path('admin/users/', user_management, name='user_management'),
    path('admin/users/delete/<int:user_id>/', user_delete, name='user_delete'),
    path('admin/roles/', roles_permissions, name='roles_permissions'),
    path('admin/config/', system_config, name='system_config'),
    path('admin/logs/', activity_logs, name='activity_logs'),
    path('profile/', user_profile, name='user_profile'),
]
