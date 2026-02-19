from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import ActivityLog, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username',
        'first_name',
        'last_name',
        'email',
        'role',
        'teaching_grade',
        'teaching_section',
        'is_polyteacher',
        'is_active',
    )
    list_filter = (
        'role',
        'is_active',
        'teaching_grade',
        'teaching_section',
        'is_polyteacher',
    )
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Datos academicos', {
            'fields': (
                'role',
                'phone',
                'teaching_grade',
                'teaching_section',
                'is_polyteacher',
                'teaching_courses',
                'teaching_grades',
            )
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Datos academicos', {
            'fields': (
                'role',
                'phone',
                'teaching_grade',
                'teaching_section',
                'is_polyteacher',
                'teaching_courses',
                'teaching_grades',
            )
        }),
    )


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'method', 'path', 'ip_address')
    list_filter = ('method', 'created_at')
    search_fields = ('user__username', 'path', 'ip_address', 'action')
