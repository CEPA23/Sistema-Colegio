import csv

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from academic.models import AcademicYear, Section, TeacherCourseAssignment
from core.student_ordering import (
    order_queryset_by_student_name,
    resolve_student_order,
    student_order_context,
)
from enrollment.models import Enrollment

from .forms import AttendanceSheetFilterForm
from .models import AttendanceRecord
from .reporting import (
    STATUS_LABELS,
    build_attendance_pdf,
    build_attendance_report_data,
    build_attendance_workbook,
    workbook_to_bytes,
)


STATUS_UI = {
    'present': {'label': 'Asistio', 'icon': '✓', 'css': 'attendance-present'},
    'absent': {'label': 'Falta', 'icon': 'F', 'css': 'attendance-absent'},
    'tardy': {'label': 'Tardanza', 'icon': 'T', 'css': 'attendance-tardy'},
    'justified': {'label': 'Justificado', 'icon': 'J', 'css': 'attendance-justified'},
    'missing': {'label': 'Sin registro', 'icon': '-', 'css': 'attendance-missing'},
}
VALID_STATUSES = {status for status, _ in AttendanceRecord.STATUS}


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


def _resolve_academic_year(selected_date):
    year_obj = AcademicYear.objects.filter(year=selected_date.year).first()
    if year_obj:
        return year_obj
    return AcademicYear.objects.filter(is_active=True).order_by('-year').first()


def _active_enrollments_for_section(selected_section, selected_date, student_order='az'):
    enrollment_filters = {
        'status': 'active',
        'section': selected_section,
    }
    year_obj = _resolve_academic_year(selected_date)
    if year_obj:
        enrollment_filters['academic_year'] = year_obj
    return order_queryset_by_student_name(
        Enrollment.objects.select_related('student').filter(**enrollment_filters),
        prefix='student',
        student_order=student_order,
    )


def _build_rows(enrollments, records_by_enrollment, default_status='present'):
    rows = []
    fallback_ui = STATUS_UI.get(default_status, STATUS_UI['present'])
    for enrollment in enrollments:
        record = records_by_enrollment.get(enrollment.id)
        status = record.status if record else default_status
        rows.append({
            'enrollment': enrollment,
            'status': status,
            'note': record.note if record else '',
            'has_record': bool(record),
            'ui': STATUS_UI.get(status, fallback_ui),
        })
    return rows


def _owner_name(owner_record):
    if not owner_record or not owner_record.recorded_by:
        return 'otro docente'
    full_name = owner_record.recorded_by.get_full_name().strip()
    return full_name or owner_record.recorded_by.username


def _redirect_to_filtered_sheet(path, selected_section, selected_date, student_order='az'):
    return redirect(
        f"{path}?section={selected_section.id}&date={selected_date.isoformat()}&student_order={student_order}"
    )


def _filter_form_for_request(request, today):
    student_order = resolve_student_order(request)
    is_teacher = request.user.role == 'teacher' and not request.user.is_superuser
    teacher_section_ids = _teacher_section_ids(request.user) if is_teacher else []
    auto_section_id = teacher_section_ids[0] if len(teacher_section_ids) == 1 else None

    initial = {'date': request.GET.get('date') or today}
    form_data = request.GET.copy()
    if auto_section_id:
        form_data['section'] = str(auto_section_id)
        if not form_data.get('date'):
            form_data['date'] = today.isoformat()
    filter_form = AttendanceSheetFilterForm(form_data or None, initial=initial, user=request.user)
    return filter_form, student_order, auto_section_id


def _build_month_report_from_request(request):
    today = timezone.localdate()
    filter_form, student_order, auto_section_id = _filter_form_for_request(request, today)
    selected_section = None
    selected_date = today
    report = None

    if filter_form.is_valid():
        selected_date = filter_form.cleaned_data['date']
        selected_section = filter_form.cleaned_data['section']
        report = build_attendance_report_data(
            selected_section,
            selected_date,
            student_order=student_order,
            request_user=request.user,
        )

    return {
        'filter_form': filter_form,
        'student_order': student_order,
        'auto_section_mode': bool(auto_section_id),
        'selected_section': selected_section,
        'selected_date': selected_date,
        'report': report,
    }


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
    student_order = resolve_student_order(request)
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
    enrollments = []
    rows = []
    attendance_owner = None
    can_edit = True

    if filter_form.is_valid():
        selected_date = filter_form.cleaned_data['date']
        selected_section = filter_form.cleaned_data['section']

        section_records = list(
            AttendanceRecord.objects.select_related('recorded_by').filter(
                enrollment__section=selected_section,
                date=selected_date,
            ).order_by('created_at', 'id')
        )
        existing_by_enrollment = {record.enrollment_id: record for record in section_records}

        attendance_owner_record = next(
            (record for record in section_records if record.recorded_by_id),
            None,
        )
        attendance_owner = attendance_owner_record.recorded_by if attendance_owner_record else None

        if section_records and is_teacher:
            can_edit = (
                not attendance_owner_record
                or attendance_owner_record.recorded_by_id == request.user.id
            )

        enrollments = list(
            _active_enrollments_for_section(
                selected_section,
                selected_date,
                student_order=student_order,
            )
        )

        if request.method == 'POST':
            if section_records and not can_edit:
                messages.error(
                    request,
                    (
                        f"La asistencia de esta seccion para {selected_date} ya fue "
                        f"registrada por {_owner_name(attendance_owner_record)}. "
                        'Solo puedes visualizarla.'
                    ),
                )
                return _redirect_to_filtered_sheet(
                    request.path,
                    selected_section,
                    selected_date,
                    student_order=student_order,
                )

            try:
                for enrollment in enrollments:
                    status = request.POST.get(f'status_{enrollment.id}', 'present')
                    note = request.POST.get(f'note_{enrollment.id}', '').strip()
                    if status not in VALID_STATUSES:
                        status = 'present'
                    if status != 'justified':
                        note = ''

                    existing = existing_by_enrollment.get(enrollment.id)
                    if existing:
                        update_fields = []
                        if existing.status != status:
                            existing.status = status
                            update_fields.append('status')
                        if existing.note != note:
                            existing.note = note
                            update_fields.append('note')
                        if existing.recorded_by_id is None:
                            existing.recorded_by = request.user
                            update_fields.append('recorded_by')
                        if update_fields:
                            existing.full_clean()
                            existing.save(update_fields=update_fields)
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
                messages.error(request, '; '.join(exc.messages))
                return _redirect_to_filtered_sheet(
                    request.path,
                    selected_section,
                    selected_date,
                    student_order=student_order,
                )

            messages.success(request, 'Asistencia guardada correctamente.')
            return _redirect_to_filtered_sheet(
                request.path,
                selected_section,
                selected_date,
                student_order=student_order,
            )

        rows = _build_rows(enrollments, existing_by_enrollment, default_status='present')

    context = {
        'filter_form': filter_form,
        'selected_section': selected_section,
        'selected_date': selected_date,
        'rows': rows,
        'status_ui': STATUS_UI,
        'can_edit': can_edit,
        'attendance_owner': attendance_owner,
        'auto_section_mode': bool(auto_section_id),
    }
    context.update(student_order_context(request, student_order))
    return render(request, 'attendance/attendance_form.html', context)


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
    context = _build_month_report_from_request(request)
    context.update(student_order_context(request, context['student_order']))
    return render(request, 'attendance/course_report.html', context)


@role_required('admin', 'director', 'teacher')
def attendance_export_excel(request):
    context = _build_month_report_from_request(request)
    if not context['report'] or not context['selected_section']:
        raise Http404('Debes seleccionar una seccion y una fecha validas.')

    workbook = build_attendance_workbook(context['report'])
    filename = (
        f"asistencia_{context['selected_section'].grade.name}_{context['selected_section'].name}_"
        f"{context['selected_date'].strftime('%Y_%m')}.xlsx"
    ).replace(' ', '_')
    response = HttpResponse(
        workbook_to_bytes(workbook),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@role_required('admin', 'director', 'teacher')
def attendance_export_pdf(request):
    context = _build_month_report_from_request(request)
    if not context['report'] or not context['selected_section']:
        raise Http404('Debes seleccionar una seccion y una fecha validas.')

    filename = (
        f"asistencia_{context['selected_section'].grade.name}_{context['selected_section'].name}_"
        f"{context['selected_date'].strftime('%Y_%m')}.pdf"
    ).replace(' ', '_')
    response = HttpResponse(
        build_attendance_pdf(context['report']),
        content_type='application/pdf',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@role_required('admin', 'director', 'teacher')
def attendance_export_csv(request):
    is_teacher = request.user.role == 'teacher' and not request.user.is_superuser
    student_order = resolve_student_order(request)
    records = AttendanceRecord.objects.select_related(
        'enrollment__student',
        'enrollment__section__grade',
        'recorded_by',
    )

    if is_teacher:
        records = records.filter(enrollment__section_id__in=_teacher_section_ids(request.user))

    section_id = request.GET.get('section')
    if section_id:
        records = records.filter(enrollment__section_id=section_id)

    date_value = request.GET.get('date')
    if date_value:
        records = records.filter(date__month=date_value[5:7], date__year=date_value[:4])

    records = order_queryset_by_student_name(
        records,
        prefix='enrollment__student',
        student_order=student_order,
        extra_fields=['date', 'id'],
    )

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
            STATUS_LABELS.get(record.status, record.get_status_display()),
            recorded_by,
            record.note,
        ])

    return response
