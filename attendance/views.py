import csv
import calendar
from datetime import date as date_class

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from academic.models import AcademicYear
from academic.models import Grade, Section
from core.student_ordering import (
    order_queryset_by_student_name,
    resolve_student_order,
    student_order_context,
)
from core.teacher_access import teacher_section_ids, teacher_tutor_section_ids
from enrollment.models import Enrollment
from students.models import Student

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


def _student_report_students(user):
    students = Student.objects.filter(enrollment__isnull=False).distinct()
    if user.role == 'teacher' and not user.is_superuser:
        students = students.filter(
            enrollment__section_id__in=teacher_tutor_section_ids(user),
        ).distinct()
    return students.order_by('last_name', 'first_name', 'dni')


def _student_report_grades(user):
    grades = Grade.objects.filter(section__isnull=False).distinct()
    if user.role == 'teacher' and not user.is_superuser:
        grades = grades.filter(section__id__in=teacher_tutor_section_ids(user)).distinct()
    return grades.order_by('name')


def _student_report_sections(user, grade_id=None):
    sections = Section.objects.select_related('grade').order_by('grade__name', 'name')
    if user.role == 'teacher' and not user.is_superuser:
        sections = sections.filter(id__in=teacher_tutor_section_ids(user))
    if grade_id and str(grade_id).isdigit():
        sections = sections.filter(grade_id=int(grade_id))
    return sections


def _student_report_all_sections(user):
    sections = Section.objects.select_related('grade').order_by('grade__name', 'name')
    if user.role == 'teacher' and not user.is_superuser:
        sections = sections.filter(id__in=teacher_tutor_section_ids(user))
    return sections


def _student_report_maps(user):
    all_sections = list(_student_report_all_sections(user))
    grade_section_map = {}
    section_student_map = {}

    for section in all_sections:
        grade_section_map.setdefault(str(section.grade_id), []).append({
            'id': section.id,
            'label': section.name,
        })
        section_student_map[str(section.id)] = _student_report_students_by_section(user, section.id)

    return all_sections, grade_section_map, section_student_map


def _student_report_students_by_section(user, section_id):
    enrollments = Enrollment.objects.select_related(
        'student',
        'section__grade',
        'academic_year',
    ).filter(section_id=section_id)
    if user.role == 'teacher' and not user.is_superuser:
        enrollments = enrollments.filter(section_id__in=teacher_tutor_section_ids(user))
    enrollments = enrollments.order_by('student__last_name', 'student__first_name', 'student__dni')
    return [
        {
            'id': enrollment.student_id,
            'name': str(enrollment.student),
            'enrollment_id': enrollment.id,
        }
        for enrollment in enrollments
    ]


def _student_report_enrollment(user, student, section_id=None):
    enrollments = Enrollment.objects.select_related(
        'student',
        'section__grade',
        'academic_year',
    ).filter(student=student).order_by('-enrolled_at', '-id')

    if user.role == 'teacher' and not user.is_superuser:
        enrollments = enrollments.filter(section_id__in=teacher_tutor_section_ids(user))
    if section_id and str(section_id).isdigit():
        enrollments = enrollments.filter(section_id=int(section_id))

    return enrollments.first()


def _student_report_context(request, selected_student=None, selected_month=None, selected_grade_id=None, selected_section_id=None):
    if not selected_grade_id and request.user.role == 'teacher' and not request.user.is_superuser:
        accessible_sections = list(_student_report_all_sections(request.user))
        if len(accessible_sections) == 1:
            selected_grade_id = str(accessible_sections[0].grade_id)
            selected_section_id = str(accessible_sections[0].id)

    grades = _student_report_grades(request.user)
    sections = _student_report_sections(request.user, selected_grade_id)
    student_options = _student_report_students_by_section(request.user, selected_section_id) if selected_section_id else []
    all_sections, grade_section_map, section_student_map = _student_report_maps(request.user)
    selected_enrollment = None
    records = AttendanceRecord.objects.none()
    summary = {
        'present': 0,
        'absent': 0,
        'tardy': 0,
        'justified': 0,
    }

    if selected_student is not None:
        selected_enrollment = _student_report_enrollment(request.user, selected_student, selected_section_id)
        if not selected_enrollment:
            messages.error(request, "No tienes permiso para ver el reporte de este alumno.")
            return {
                'grade_options': grades,
                'section_options': sections,
                'student_options': student_options,
                'all_section_options': all_sections,
                'grade_section_map': grade_section_map,
                'section_student_map': section_student_map,
                'selected_student': None,
                'selected_enrollment': None,
                'records': records,
                'summary': summary,
                'selected_month': selected_month,
                'selected_grade_id': selected_grade_id,
                'selected_section_id': selected_section_id,
                'selected_student_id': None,
            }

        records = AttendanceRecord.objects.select_related(
            'enrollment__section__grade',
            'recorded_by',
        ).filter(enrollment=selected_enrollment)

        if selected_month:
            month_end_day = calendar.monthrange(selected_month.year, selected_month.month)[1]
            records = records.filter(
                date__gte=selected_month,
                date__lte=date_class(selected_month.year, selected_month.month, month_end_day),
            )

        records = records.order_by('-date', '-id')
        for record in records:
            if record.status in summary:
                summary[record.status] += 1

    return {
        'grade_options': grades,
        'section_options': sections,
        'student_options': student_options,
        'all_section_options': all_sections,
        'grade_section_map': grade_section_map,
        'section_student_map': section_student_map,
        'selected_student': selected_student,
        'selected_student_label': str(selected_student) if selected_student else '',
        'selected_enrollment': selected_enrollment,
        'records': records,
        'summary': summary,
        'selected_month': selected_month,
        'selected_grade_id': selected_grade_id,
        'selected_section_id': selected_section_id,
        'selected_student_id': selected_student.id if selected_student else None,
    }


def _redirect_to_filtered_sheet(path, selected_section, selected_date, student_order='az'):
    return redirect(
        f"{path}?section={selected_section.id}&date={selected_date.isoformat()}&student_order={student_order}"
    )


def _filter_form_for_request(request, today):
    student_order = resolve_student_order(request)
    is_teacher = request.user.role == 'teacher' and not request.user.is_superuser
    section_ids = teacher_section_ids(request.user) if is_teacher else []
    auto_section_id = section_ids[0] if len(section_ids) == 1 else None

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
    section_ids = teacher_section_ids(request.user) if is_teacher else []
    auto_section_id = section_ids[0] if len(section_ids) == 1 else None

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
    if request.user.role == 'teacher' and not request.user.is_superuser:
        if enrollment.section_id not in set(teacher_tutor_section_ids(request.user)):
            messages.error(request, "No tienes permiso para ver el reporte de este alumno.")
            return redirect('student_list')

    month_value = (request.GET.get('month') or '').strip()
    selected_month = None
    if month_value:
        try:
            selected_month = date_class.fromisoformat(f'{month_value}-01')
        except ValueError:
            selected_month = None

    records = AttendanceRecord.objects.select_related(
        'enrollment__section__grade',
        'recorded_by',
    ).filter(enrollment=enrollment)
    if selected_month:
        month_end_day = calendar.monthrange(selected_month.year, selected_month.month)[1]
        records = records.filter(
            date__gte=selected_month,
            date__lte=date_class(selected_month.year, selected_month.month, month_end_day),
        )
    records = records.order_by('-date', '-id')
    summary = {
        'present': 0,
        'absent': 0,
        'tardy': 0,
        'justified': 0,
    }
    for record in records:
        if record.status in summary:
            summary[record.status] += 1

    all_sections, grade_section_map, section_student_map = _student_report_maps(request.user)
    context = {
        'enrollment': enrollment,
        'selected_enrollment': enrollment,
        'selected_student': enrollment.student,
        'selected_student_id': enrollment.student_id,
        'selected_student_label': str(enrollment.student),
        'records': records,
        'summary': summary,
        'selected_month': selected_month,
        'status_ui': STATUS_UI,
        'grade_options': _student_report_grades(request.user),
        'section_options': _student_report_sections(request.user, enrollment.section.grade_id),
        'student_options': _student_report_students_by_section(request.user, enrollment.section_id),
        'all_section_options': all_sections,
        'grade_section_map': grade_section_map,
        'section_student_map': section_student_map,
        'selected_grade_id': enrollment.section.grade_id,
        'selected_section_id': enrollment.section_id,
    }
    return render(request, 'attendance/student_history.html', context)


@role_required('admin', 'director', 'teacher')
def attendance_student_report(request):
    month_value = (request.GET.get('month') or '').strip()
    selected_month = None
    if month_value:
        try:
            selected_month = date_class.fromisoformat(f'{month_value}-01')
        except ValueError:
            selected_month = None

    selected_grade_id = request.GET.get('grade')
    selected_section_id = request.GET.get('section')
    selected_student = None
    student_id = request.GET.get('student')
    if student_id and str(student_id).isdigit():
        student_queryset = _student_report_students(request.user)
        selected_student = student_queryset.filter(id=int(student_id)).first()
        if not selected_student:
            messages.error(request, "No tienes permiso para ver ese alumno.")

    context = _student_report_context(
        request,
        selected_student,
        selected_month,
        selected_grade_id=selected_grade_id,
        selected_section_id=selected_section_id,
    )
    if context['selected_enrollment']:
        context['enrollment'] = context['selected_enrollment']
    context['status_ui'] = STATUS_UI
    return render(request, 'attendance/student_history.html', context)


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
        records = records.filter(enrollment__section_id__in=teacher_section_ids(request.user))

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
