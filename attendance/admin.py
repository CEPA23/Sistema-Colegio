from django.contrib import admin

from .models import AttendanceRecord


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        'date',
        'section_label',
        'enrollment',
        'status',
        'recorded_by',
    )
    list_filter = (
        'date',
        'status',
        'enrollment__section__grade',
        'enrollment__section',
    )
    search_fields = (
        'enrollment__student__first_name',
        'enrollment__student__last_name',
        'note',
    )

    @staticmethod
    def section_label(obj):
        return f"{obj.enrollment.section.grade} {obj.enrollment.section.name}"
