from django.contrib import admin
from django.db import transaction

from .models import (
    AcademicYear,
    Competency,
    Course,
    Grade,
    GradeRecord,
    Indicator,
    IndicatorGrade,
    Period,
    Section,
    TeacherCourseAssignment,
)


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ('year', 'school', 'is_active')
    list_filter = ('is_active', 'school')
    search_fields = ('year', 'school__name')


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'grade')
    list_filter = ('grade',)
    search_fields = ('name', 'grade__name')


class IndicatorInline(admin.TabularInline):
    model = Indicator
    extra = 1


@admin.register(Competency)
class CompetencyAdmin(admin.ModelAdmin):
    list_display = ('name', 'course', 'order')
    list_filter = ('course',)
    search_fields = ('name', 'course__name')
    inlines = [IndicatorInline]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'academic_year', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'academic_year__year')
    search_fields = ('name', 'academic_year__year')
    actions = ('activate_period',)

    @admin.action(description='Activar periodo seleccionado')
    def activate_period(self, request, queryset):
        if not queryset.exists():
            return
        period = queryset.first()
        with transaction.atomic():
            Period.objects.filter(is_active=True).exclude(id=period.id).update(is_active=False)
            period.is_active = True
            period.save(update_fields=['is_active'])

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if obj.is_active:
                Period.objects.filter(is_active=True).exclude(id=obj.id).update(is_active=False)
            super().save_model(request, obj, form, change)


@admin.register(TeacherCourseAssignment)
class TeacherCourseAssignmentAdmin(admin.ModelAdmin):
    list_display = ('course', 'teacher', 'grade', 'section', 'academic_year')
    list_filter = ('academic_year__year', 'grade', 'section', 'teacher')
    search_fields = (
        'course__name',
        'teacher__username',
        'teacher__first_name',
        'teacher__last_name',
        'section__name',
    )


@admin.register(GradeRecord)
class GradeRecordAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'course', 'period', 'grade')
    list_filter = ('period', 'course')
    search_fields = (
        'enrollment__student__first_name',
        'enrollment__student__last_name',
        'course__name',
    )


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = ('name', 'competency', 'order')
    list_filter = ('competency__course',)
    search_fields = ('name', 'competency__name', 'competency__course__name')


@admin.register(IndicatorGrade)
class IndicatorGradeAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'indicator', 'period', 'grade')
    list_filter = ('period', 'indicator__competency__course', 'grade')
    search_fields = (
        'enrollment__student__first_name',
        'enrollment__student__last_name',
        'indicator__name',
    )
