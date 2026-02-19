from django.contrib import admin

from .models import AttendanceRecord


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        'date',
        'assignment',
        'enrollment',
        'status',
        'recorded_by',
    )
    list_filter = (
        'date',
        'status',
        'assignment__course',
        'assignment__section',
    )
    search_fields = (
        'enrollment__student__first_name',
        'enrollment__student__last_name',
        'assignment__course__name',
        'note',
    )
