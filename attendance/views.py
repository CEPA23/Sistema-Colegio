import csv

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from academic.models import AcademicYear, Section, TeacherCourseAssignment
from enrollment.models import Enrollment

from .forms import AttendanceSheetFilterForm
from .models import AttendanceRecord


STATUS_UI = {
    'present': {'label': 'Asistio', 'icon': '✔', 'css': 'attendance-present'},
    'absent': {'label': 'Falto', 'icon': '❌', 'css': 'attendance-absent'},
    'justified': {'label': 'Justificado', 'icon': '✔', 'css': 'attendance-justified'},
}


def _teacher_section_ids(user):
    assignment_section_ids = TeacherCourseAssignment.objects.filter(
        teacher=user,
        section__isnull=False,
    ).values_list('section_id', flat=True).distinct()
    tutor_section_ids = Section.objects.filter(
        tutor_teacher=user,
    ).values_list('id', flat=True)
    profile_section_ids = []
    if user.teaching_section_id:
        profile_section_ids.append(user.teaching_section_id)
    profile_section_ids.extend(user.teaching_sections.values_list('id', flat=True))
    return sorted(set(assignment_section_ids).union(tutor_section_ids, profile_section_ids))


@role_required('admin', 'director', 'teacher')
def attendance_dashboard(request):
    today = timezone.localdate()
    context = {
        'today': today,
        'today_records': AttendanceRecord.objects.filter(date=today).count(),
        'total_records': AttendanceRecord.objects.count(),
        'total_absences': AttendanceRecord.objects.filter(status='absent').count(),
    }
    return render(request, 'attendance/attendance_dashboard.html', context)


@role_required('admin', 'director', 'teacher')
def attendance_take(request):
    today = timezone.localdate()
    initial = {'date': request.GET.get('date') or today}
    is_teacher = request.user.role == 'teacher' and not request.user.is_superuser
    teacher_section_ids = _teacher_section_ids(request.user) if is_teacher else []
    auto_section_id = teacher_section_ids[0] if len(teacher_section_ids) == 1 else None

    if request.method == 'POST':
        form_data = request.POST.copy()
        if auto_section_id:
            form_data['section'] = str(auto_section_id)
        filter_form = AttendanceSheetFilterForm(form_data, user=request.user)
    else:
        form_data = request.GET.copy()
        if auto_section_id:
            form_data['section'] = str(auto_section_id)
            if not form_data.get('date'):
                form_data['date'] = today.isoformat()
        filter_form = AttendanceSheetFilterForm(form_data or None, initial=initial, user=request.user)

    selected_section = None
    selected_date = today
    enrollments = Enrollment.objects.none()
    rows = []
    section_records = AttendanceRecord.objects.none()
    attendance_owner = None
    can_edit = True
    if filter_form.is_valid():
        selected_date = filter_form.cleaned_data['date']
        selected_section = filter_form.cleaned_data['section']

        section_records = AttendanceRecord.objects.select_related(
            'recorded_by',
            'enrollment__student',
            'enrollment__section__grade',
        ).filter(
            enrollment__section=selected_section,
            date=selected_date,
        ).order_by('created_at', 'id')

        attendance_owner = section_records.exclude(recorded_by__isnull=True).first()
        if section_records.exists() and is_teacher:
            can_edit = not attendance_owner or attendance_owner.recorded_by_id == request.user.id

        year_obj = AcademicYear.objects.filter(year=selected_date.year).first()
        if not year_obj:
            year_obj = AcademicYear.objects.filter(is_active=True).order_by('-year').first()

        enrollment_filters = {
            'status': 'active',
            'section': selected_section,
        }
        if year_obj:
            enrollment_filters['academic_year'] = year_obj

        enrollments = Enrollment.objects.select_related('student').filter(
            **enrollment_filters
        ).order_by('student__last_name', 'student__first_name')

        if request.method == 'POST':
            if section_records.exists() and not can_edit:
                owner_name = (
                    attendance_owner.recorded_by.get_full_name().strip()
                    if attendance_owner and attendance_owner.recorded_by
                    else ''
                )
                owner_name = owner_name or (
                    attendance_owner.recorded_by.username
                    if attendance_owner and attendance_owner.recorded_by
                    else 'otro docente'
                )
                messages.error(
                    request,
                    f"La asistencia de esta seccion para {selected_date} ya fue registrada por {owner_name}. Solo puedes visualizarla."
                )
                return redirect(
                    f"{request.path}?section={selected_section.id}&date={selected_date.isoformat()}"
                )

            valid_statuses = set(dict(AttendanceRecord.STATUS).keys())
            existing_by_enrollment = {record.enrollment_id: record for record in section_records}
            try:
                for enrollment in enrollments:
                    status = request.POST.get(f'status_{enrollment.id}', 'present')
                    note = request.POST.get(f'note_{enrollment.id}', '').strip()
                    if status not in valid_statuses:
                        status = 'present'

                    existing = existing_by_enrollment.get(enrollment.id)
                    if existing:
                        existing.status = status
                        existing.note = note
                        if existing.recorded_by_id is None:
                            existing.recorded_by = request.user
                        existing.full_clean()
                        existing.save(update_fields=['status', 'note', 'recorded_by'])
                    else:
                        new_record = AttendanceRecord(
                            enrollment=enrollment,
                            assignment=None,
                            date=selected_date,
                            status=status,
                            note=note,
                            recorded_by=request.user,
                        )
                        new_record.full_clean()
                        new_record.save()
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect(
                    f"{request.path}?section={selected_section.id}&date={selected_date.isoformat()}"
                )

            messages.success(request, 'Asistencia guardada correctamente.')
            return redirect(
                f"{request.path}?section={selected_section.id}&date={selected_date.isoformat()}"
            )

        records = AttendanceRecord.objects.filter(
            enrollment__section=selected_section,
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
        'selected_section': selected_section,
        'selected_date': selected_date,
        'rows': rows,
        'status_ui': STATUS_UI,
        'status_choices': AttendanceRecord.STATUS,
        'can_edit': can_edit,
        'attendance_owner': attendance_owner.recorded_by if attendance_owner else None,
        'auto_section_mode': bool(auto_section_id),
    })


@role_required('admin', 'director', 'teacher', 'parent')
def attendance_student_history(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment.objects.select_related('student'), id=enrollment_id)
    records = AttendanceRecord.objects.select_related(
        'enrollment__section__grade',
        'recorded_by',
    ).filter(enrollment=enrollment)
    return render(request, 'attendance/student_history.html', {
        'enrollment': enrollment,
        'records': records,
        'status_ui': STATUS_UI,
    })


@role_required('admin', 'director', 'teacher')
def attendance_course_report(request):
    is_teacher = request.user.role == 'teacher' and not request.user.is_superuser

    records = AttendanceRecord.objects.select_related(
        'enrollment__section__grade',
        'recorded_by',
    )
    assigned_section_ids = []

    if is_teacher:
        assigned_section_ids = _teacher_section_ids(request.user)
        records = records.filter(enrollment__section_id__in=assigned_section_ids)

    section_id = request.GET.get('section')
    if section_id:
        records = records.filter(enrollment__section_id=section_id)

    summary = records.values(
        'date',
        'enrollment__section__grade__name',
        'enrollment__section__name',
        'recorded_by__first_name',
        'recorded_by__last_name',
        'recorded_by__username',
    ).annotate(
        total=Count('id'),
        present=Count('id', filter=models.Q(status='present')),
        absent=Count('id', filter=models.Q(status='absent')),
        justified=Count('id', filter=models.Q(status='justified')),
    ).order_by(
        '-date',
        'enrollment__section__grade__name',
        'enrollment__section__name',
    )

    sections = Section.objects.select_related('grade').order_by('grade__name', 'name')
    if is_teacher:
        sections = sections.filter(id__in=assigned_section_ids)

    return render(request, 'attendance/course_report.html', {
        'summary': summary,
        'section_id': section_id,
        'sections': sections,
    })



@role_required('admin', 'director', 'teacher')
def attendance_export_csv(request):
    records = AttendanceRecord.objects.select_related(
        'enrollment__student',
        'enrollment__section__grade',
        'recorded_by',
    ).order_by('-date')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="asistencias.csv"'
    writer = csv.writer(response)
    writer.writerow(['Fecha', 'Seccion', 'Alumno', 'Estado', 'Registrado por', 'Observacion'])

    for record in records:
        section_label = f"{record.enrollment.section.grade.name} {record.enrollment.section.name}"
        recorded_by = '-'
        if record.recorded_by:
            recorded_by = record.recorded_by.get_full_name().strip() or record.recorded_by.username

        writer.writerow([
            record.date,
            section_label,
            str(record.enrollment.student),
            record.get_status_display(),
            recorded_by,
            record.note,
        ])

    return response
