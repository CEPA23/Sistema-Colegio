import csv

from django.contrib import messages
from django.db import models
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from academic.models import TeacherCourseAssignment
from enrollment.models import Enrollment

from .forms import AttendanceSheetFilterForm
from .models import AttendanceRecord


STATUS_UI = {
    'present': {'label': 'Asistio', 'icon': '✔', 'css': 'attendance-present'},
    'absent': {'label': 'Falto', 'icon': '❌', 'css': 'attendance-absent'},
    'justified': {'label': 'Justificado', 'icon': '✔', 'css': 'attendance-justified'},
}


@role_required('admin', 'director', 'teacher', 'secretary')
def attendance_dashboard(request):
    today = timezone.localdate()
    context = {
        'today': today,
        'today_records': AttendanceRecord.objects.filter(date=today).count(),
        'total_records': AttendanceRecord.objects.count(),
        'total_absences': AttendanceRecord.objects.filter(status='absent').count(),
    }
    return render(request, 'attendance/attendance_dashboard.html', context)


@role_required('admin', 'director', 'teacher', 'secretary')
def attendance_take(request):
    today = timezone.localdate()
    initial = {'date': request.GET.get('date') or today}

    if request.method == 'POST':
        filter_form = AttendanceSheetFilterForm(request.POST, user=request.user)
    else:
        filter_form = AttendanceSheetFilterForm(request.GET or None, initial=initial, user=request.user)

    selected_assignment = None
    selected_date = today
    enrollments = Enrollment.objects.none()
    rows = []

    if filter_form.is_valid():
        selected_date = filter_form.cleaned_data['date']
        selected_assignment = filter_form.cleaned_data['assignment']
        
        enrollment_filters = {
            'academic_year': selected_assignment.academic_year,
            'status': 'active'
        }
        if selected_assignment.section_id:
            enrollment_filters['section_id'] = selected_assignment.section_id
        elif selected_assignment.grade_id:
            enrollment_filters['section__grade_id'] = selected_assignment.grade_id
        elif selected_assignment.level_id:
            enrollment_filters['section__grade__level_id'] = selected_assignment.level_id

        enrollments = Enrollment.objects.select_related('student').filter(
            **enrollment_filters
        ).order_by('student__last_name', 'student__first_name')

        if request.method == 'POST':
            valid_statuses = set(dict(AttendanceRecord.STATUS).keys())
            for enrollment in enrollments:
                status = request.POST.get(f'status_{enrollment.id}', 'present')
                note = request.POST.get(f'note_{enrollment.id}', '').strip()
                if status not in valid_statuses:
                    status = 'present'

                AttendanceRecord.objects.update_or_create(
                    enrollment=enrollment,
                    assignment=selected_assignment,
                    date=selected_date,
                    defaults={
                        'status': status,
                        'note': note,
                        'recorded_by': request.user,
                    }
                )

            messages.success(request, 'Asistencia guardada correctamente.')
            return redirect(
                f"{request.path}?assignment={selected_assignment.id}&date={selected_date.isoformat()}"
            )

        records = AttendanceRecord.objects.filter(
            assignment=selected_assignment,
            date=selected_date,
            enrollment__in=enrollments
        )
        by_enrollment = {record.enrollment_id: record for record in records}

        for enrollment in enrollments:
            record = by_enrollment.get(enrollment.id)
            status = record.status if record else 'present'
            rows.append({
                'enrollment': enrollment,
                'status': status,
                'note': record.note if record else '',
                'ui': STATUS_UI.get(status, STATUS_UI['present']),
            })

    return render(request, 'attendance/attendance_form.html', {
        'filter_form': filter_form,
        'selected_assignment': selected_assignment,
        'selected_date': selected_date,
        'rows': rows,
        'status_ui': STATUS_UI,
        'status_choices': AttendanceRecord.STATUS,
    })


@role_required('admin', 'director', 'teacher', 'secretary', 'parent')
def attendance_student_history(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment.objects.select_related('student'), id=enrollment_id)
    records = AttendanceRecord.objects.select_related(
        'assignment__course',
        'assignment__section__grade',
    ).filter(enrollment=enrollment)
    return render(request, 'attendance/student_history.html', {
        'enrollment': enrollment,
        'records': records,
        'status_ui': STATUS_UI,
    })


@role_required('admin', 'director', 'teacher', 'secretary')
def attendance_course_report(request):
    is_teacher = request.user.role == 'teacher' and not request.user.is_superuser
    
    records = AttendanceRecord.objects.select_related(
        'assignment__course',
        'assignment__section__grade__level',
        'assignment__grade',
        'assignment__level',
    ).filter(assignment__isnull=False) # Exclude records without assignment

    if is_teacher:
        assigned_course_ids = TeacherCourseAssignment.objects.filter(teacher=request.user).values_list('course_id', flat=True)
        records = records.filter(assignment__teacher=request.user)

    assignment_id = request.GET.get('assignment')
    if assignment_id:
        records = records.filter(assignment_id=assignment_id)

    summary = records.values(
        'assignment__id',
        'assignment__course__name',
        'assignment__level__name',
        'assignment__grade__name',
        'assignment__section__name',
    ).annotate(
        total=Count('id'),
        present=Count('id', filter=models.Q(status='present')),
        absent=Count('id', filter=models.Q(status='absent')),
        justified=Count('id', filter=models.Q(status='justified')),
    ).order_by(
        'assignment__level__name',
        'assignment__grade__name',
        'assignment__section__name',
        'assignment__course__name',
    )

    assignments = TeacherCourseAssignment.objects.select_related(
        'course',
        'section__grade',
        'grade',
        'level',
        'academic_year',
    ).order_by(
        '-academic_year__year',
        'course__name',
    )
    
    if is_teacher:
        assignments = assignments.filter(teacher=request.user)

    return render(request, 'attendance/course_report.html', {
        'summary': summary,
        'assignment_id': assignment_id,
        'assignments': assignments,
    })



@role_required('admin', 'director', 'teacher', 'secretary')
def attendance_export_csv(request):
    records = AttendanceRecord.objects.select_related(
        'enrollment__student',
        'assignment__course',
        'assignment__section__grade',
    ).order_by('-date')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="asistencias.csv"'
    writer = csv.writer(response)
    writer.writerow(['Fecha', 'Curso', 'Alumno', 'Estado', 'Observacion'])

    for record in records:
        course_label = '-'
        if record.assignment_id:
            a = record.assignment
            course_label = f"{a.course.name} | "
            if a.section:
                course_label += f"{a.section.grade.name} {a.section.name}"
            elif a.grade:
                course_label += f"{a.grade.name}"
            elif a.level:
                course_label += f"{a.level.name}"

        writer.writerow([
            record.date,
            course_label,
            str(record.enrollment.student),
            record.get_status_display(),
            record.note,
        ])

    return response
