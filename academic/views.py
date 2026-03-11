from io import BytesIO
from collections import defaultdict

from django.contrib import messages
from django.db import models, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from accounts.models import User
from enrollment.models import Enrollment

from .forms import CompetencyForm, CourseForm, GradeForm, GradeRecordForm, IndicatorForm, SectionForm
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
    calculate_mode_grade,
    GradeSubmissionLock,
)


@role_required('admin', 'director')
def manage_grade_locks(request):
    """View for Director to see and toggle submission locks."""
    active_year = AcademicYear.objects.filter(is_active=True).first()
    if not active_year:
        messages.error(request, "No hay un año académico activo.")
        return redirect('academic_dashboard')

    assignments = TeacherCourseAssignment.objects.filter(academic_year=active_year).select_related('teacher', 'course', 'section__grade')
    periods = Period.objects.filter(academic_year=active_year).order_by('name')
    
    # Pre-build a lookup dictionary for locks: (teacher_id, course_id, section_id, period_id) -> is_locked
    locks_qs = GradeSubmissionLock.objects.filter(period__academic_year=active_year)
    lock_lookup = {
        (l.teacher_id, l.course_id, l.section_id, l.period_id): l.is_locked
        for l in locks_qs
    }

    # Flatten data for the template to avoid nested loops with complex lookups
    lock_data = []
    for assignment in assignments:
        for period in periods:
            key = (assignment.teacher_id, assignment.course_id, assignment.section_id, period.id)
            is_locked = lock_lookup.get(key, False)
            lock_data.append({
                'assignment': assignment,
                'period': period,
                'is_locked': is_locked,
                'key': f"{assignment.teacher_id}_{assignment.course_id}_{assignment.section_id}_{period.id}"
            })
    
    context = {
        'lock_data': lock_data,
    }
    return render(request, 'academic/manage_grade_locks.html', context)


@role_required('admin', 'director')
def toggle_grade_lock(request):
    """Director toggles the lock for a specific submission."""
    if request.method == 'POST':
        teacher_id = request.POST.get('teacher_id')
        course_id = request.POST.get('course_id')
        section_id = request.POST.get('section_id')
        period_id = request.POST.get('period_id')
        action = request.POST.get('action')  # 'lock' or 'unlock'
        next_url = request.POST.get('next')

        if action not in {'lock', 'unlock'}:
            messages.error(request, "Accion invalida.")
            return redirect(next_url or 'manage_grade_locks')

        section_id = section_id or None

        lock, created = GradeSubmissionLock.objects.update_or_create(
            teacher_id=teacher_id,
            course_id=course_id,
            section_id=section_id,
            period_id=period_id,
            defaults={'is_locked': (action == 'lock')}
        )
        if action == 'unlock':
            from django.utils import timezone
            lock.last_unlocked_at = timezone.now()
            lock.save()
            
        messages.success(request, f"Estado {'bloqueado' if action == 'lock' else 'habilitado'} correctamente.")

        if next_url:
            return redirect(next_url)

    return redirect('manage_grade_locks')


@role_required('admin', 'director', 'teacher')
def academic_dashboard(request):
    context = {
        'total_courses': Course.objects.count(),
        'total_grade_records': GradeRecord.objects.count(),
        'total_periods': Period.objects.count(),
        'total_assignments': TeacherCourseAssignment.objects.count(),
    }
    return render(request, 'academic/academic_dashboard.html', context)


@role_required('admin', 'director')
def course_management(request):
    edit_course = None
    edit_id = request.GET.get('edit_course')
    if edit_id:
        edit_course = get_object_or_404(Course, id=edit_id)

    if request.method == 'POST':
        course_form = CourseForm(request.POST, instance=edit_course)
        if course_form.is_valid():
            course = course_form.save()
            if edit_course:
                messages.success(request, f"Curso '{course.name}' actualizado.")
            else:
                messages.success(request, f"Curso '{course.name}' creado correctamente.")
            return redirect('course_management')
    else:
        course_form = CourseForm(instance=edit_course)

    courses = Course.objects.order_by('name')
    context = {
        'course_form': course_form,
        'courses': courses,
        'edit_course': edit_course,
    }
    return render(request, 'academic/course_management.html', context)


@role_required('admin', 'director')
def grade_management(request):
    edit_grade = None
    edit_id = request.GET.get('edit_grade')
    if edit_id:
        edit_grade = get_object_or_404(Grade, id=edit_id)

    if request.method == 'POST':
        form = GradeForm(request.POST, instance=edit_grade)
        if form.is_valid():
            grade = form.save()
            if edit_grade:
                messages.success(request, f"Grado '{grade.name}' actualizado.")
            else:
                messages.success(request, f"Grado '{grade.name}' creado correctamente.")
            return redirect('grade_management')
    else:
        form = GradeForm(instance=edit_grade)

    grades = Grade.objects.order_by('name')
    return render(request, 'academic/grade_management.html', {
        'form': form,
        'grades': grades,
        'edit_grade': edit_grade,
    })


@role_required('admin', 'director')
def section_management(request):
    edit_section = None
    previous_tutor_id = None
    edit_id = request.GET.get('edit_section')
    if edit_id:
        edit_section = get_object_or_404(Section, id=edit_id)
        previous_tutor_id = edit_section.tutor_teacher_id

    if request.method == 'POST':
        form = SectionForm(request.POST, instance=edit_section)
        if form.is_valid():
            section = form.save()
            tutor = section.tutor_teacher
            if tutor:
                # Sync tutor assignment with teacher classroom profile.
                user_updates = {}
                if tutor.teaching_grade_id != section.grade_id:
                    user_updates['teaching_grade_id'] = section.grade_id
                if tutor.teaching_section_id != section.id:
                    user_updates['teaching_section_id'] = section.id
                if user_updates:
                    User.objects.filter(pk=tutor.pk).update(**user_updates)

            if previous_tutor_id and previous_tutor_id != section.tutor_teacher_id:
                # If previous tutor pointed to this section, clear stale profile section.
                User.objects.filter(
                    pk=previous_tutor_id,
                    teaching_section_id=section.id,
                ).update(teaching_section=None)

            if edit_section:
                messages.success(request, f"Sección '{section.name}' actualizada.")
            else:
                messages.success(request, f"Sección '{section.name}' creada para '{section.grade.name}'.")
            return redirect('section_management')
    else:
        form = SectionForm(instance=edit_section)

    sections = Section.objects.select_related('grade', 'tutor_teacher').order_by('grade__name', 'name')
    return render(request, 'academic/section_management.html', {
        'form': form,
        'sections': sections,
        'edit_section': edit_section,
    })


@role_required('admin', 'director', 'teacher')
def grade_list(request):
    grades = GradeRecord.objects.select_related(
        'enrollment__student',
        'course',
        'period'
    ).order_by('enrollment__student__last_name', 'course__name', 'period__name')

    if request.user.role == 'teacher' and not request.user.is_superuser:
        # Filter grades by courses assigned to the teacher
        assigned_course_ids = TeacherCourseAssignment.objects.filter(
            teacher=request.user
        ).values_list('course_id', flat=True)
        grades = grades.filter(course_id__in=assigned_course_ids)

    return render(request, 'academic/grade_list.html', {
        'grades': grades
    })


@role_required('admin', 'director', 'teacher')
def grade_create(request):
    if request.method == 'POST':
        form = GradeRecordForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            return redirect('grade_list')
    else:
        form = GradeRecordForm(user=request.user)

    return render(request, 'academic/grade_form.html', {
        'form': form
    })


@role_required('admin', 'director', 'teacher')
def report_card(request):
    # El reporte general siempre se consulta por grado y seccion.
    return redirect('course_report')


def _preferred_period(academic_year):
    if not academic_year:
        return None

    periods = list(
        Period.objects.filter(academic_year=academic_year).order_by('start_date', 'name')
    )
    if not periods:
        return None

    active = next((p for p in periods if p.is_active), None)
    if active:
        return active

    # Prefer "Bimestre 1" when present.
    for period in periods:
        normalized = (period.name or '').lower().replace(' ', '')
        if 'bimestre1' in normalized:
            return period

    # Otherwise, pick the earliest "bimestre".
    for period in periods:
        if 'bimestre' in (period.name or '').lower():
            return period

    return periods[0]


def _is_section_tutor(user, section):
    return bool(
        user
        and section
        and getattr(user, 'role', None) == 'teacher'
        and not getattr(user, 'is_superuser', False)
        and section.tutor_teacher_id == user.id
    )


def _courses_for_enrollment(user, enrollment):
    if not enrollment:
        return Course.objects.none()

    scope = TeacherCourseAssignment.objects.all()
    if enrollment.academic_year_id:
        scope = scope.filter(academic_year=enrollment.academic_year)

    scope = scope.filter(
        models.Q(section=enrollment.section)
        | models.Q(section__isnull=True, grade=enrollment.section.grade)
    )

    # Subject teachers only see their own courses; the tutor sees all courses of the section.
    if user.role == 'teacher' and not user.is_superuser and not _is_section_tutor(user, enrollment.section):
        scope = scope.filter(teacher=user)

    course_ids = list(scope.values_list('course_id', flat=True).distinct())
    if not course_ids:
        course_ids = list(
            GradeRecord.objects.filter(enrollment=enrollment)
            .values_list('course_id', flat=True)
            .distinct()
        )

    if not course_ids:
        return Course.objects.none()

    return Course.objects.filter(id__in=course_ids).order_by('name')


@role_required('admin', 'director', 'teacher', 'parent')
def student_report(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related('student', 'section__grade', 'academic_year'),
        id=enrollment_id
    )
    if request.user.role == 'teacher' and not request.user.is_superuser:
        if not _is_section_tutor(request.user, enrollment.section):
            messages.error(request, "Solo la tutora del aula puede generar/ver la libreta del estudiante.")
            return redirect('teacher_dashboard')
    courses = list(_courses_for_enrollment(request.user, enrollment))
    period_id = _safe_int(request.GET.get('period'))
    preferred_period = _preferred_period(enrollment.academic_year)
    if period_id and enrollment.academic_year_id:
        preferred_period = (
            Period.objects.filter(academic_year=enrollment.academic_year, id=period_id).first()
            or preferred_period
        )
    _, breakdown = _build_competency_breakdown([enrollment], courses, enrollment.academic_year)

    course_cards = []
    for course in courses:
        course_data = breakdown.get((enrollment.id, course.id), {}) or {}
        period_finals = course_data.get('period_finals', {}) or {}

        if preferred_period:
            course_grade = period_finals.get(preferred_period.id, '-') or '-'
        else:
            course_grade = course_data.get('course_final', '-') or '-'

        competency_rows = []
        for competency_row in course_data.get('competencies', []) or []:
            if preferred_period:
                competency_grade = competency_row.get('period_grades', {}).get(preferred_period.id, '-') or '-'
            else:
                competency_grade = competency_row.get('final_grade', '-') or '-'
            competency_rows.append({
                'name': competency_row.get('name', '-') or '-',
                'grade': competency_grade,
            })

        if competency_rows or course_grade != '-':
            course_cards.append({
                'course': course,
                'course_grade': course_grade,
                'competencies': competency_rows,
            })

    return render(request, 'academic/student_report.html', {
        'enrollment': enrollment,
        'preferred_period': preferred_period,
        'courses': course_cards,
    })


@role_required('admin', 'director', 'teacher')
def course_report(request):
    grade_id = _safe_int(request.GET.get('grade'))
    section_id = _safe_int(request.GET.get('section'))
    report_data = _build_grade_section_report(request.user, grade_id=grade_id, section_id=section_id)
    if request.user.role == 'teacher' and not request.user.is_superuser:
        if not report_data.get('selected_section'):
            messages.error(request, "Solo las tutoras pueden ver el reporte de notas por grado y seccion.")
            return redirect('teacher_dashboard')
    return render(request, 'academic/course_report.html', report_data)


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _active_year():
    return AcademicYear.objects.filter(is_active=True).order_by('-year').first()


def _courses_for_user(user):
    if user.role == 'teacher' and not user.is_superuser:
        assigned_course_ids = TeacherCourseAssignment.objects.filter(
            teacher=user
        ).values_list('course_id', flat=True)
        return Course.objects.filter(id__in=assigned_course_ids).order_by('name')
    return Course.objects.order_by('name')


def _is_bimestre_period_name(period_name):
    return bool(period_name and 'bimestre' in period_name.lower())


def _mode_from_period_grade_map(period_grade_map, period_name_by_id):
    all_grades = []
    bimestre_grades = []
    for period_id, grade in period_grade_map.items():
        if grade in {'AD', 'A', 'B', 'C'}:
            all_grades.append(grade)
            if _is_bimestre_period_name(period_name_by_id.get(period_id, '')):
                bimestre_grades.append(grade)
    return calculate_mode_grade(bimestre_grades or all_grades) or '-'


def _build_competency_breakdown(enrollments, courses, academic_year=None):
    enrollments = list(enrollments)
    courses = list(courses)
    if not enrollments or not courses:
        return [], {}

    periods_qs = Period.objects.all()
    if academic_year:
        periods_qs = periods_qs.filter(academic_year=academic_year)
    periods = list(periods_qs.order_by('start_date', 'name'))
    period_name_by_id = {period.id: period.name for period in periods}

    competencies = list(
        Competency.objects.filter(course__in=courses).order_by('order', 'id').prefetch_related('indicator_set')
    )
    competency_ids_by_course = defaultdict(list)
    competency_name_by_id = {}
    indicator_to_competency = {}
    for competency in competencies:
        competency_ids_by_course[competency.course_id].append(competency.id)
        competency_name_by_id[competency.id] = competency.name
        for indicator_id in competency.indicator_set.values_list('id', flat=True):
            indicator_to_competency[indicator_id] = competency.id

    indicator_ids = list(indicator_to_competency.keys())
    competency_period_raw = defaultdict(list)
    if indicator_ids:
        indicator_grades = IndicatorGrade.objects.filter(
            enrollment__in=enrollments,
            indicator_id__in=indicator_ids,
        )
        if periods:
            indicator_grades = indicator_grades.filter(period_id__in=period_name_by_id.keys())
        elif academic_year:
            indicator_grades = indicator_grades.filter(period__academic_year=academic_year)

        for enrollment_id, indicator_id, period_id, grade in indicator_grades.values_list(
            'enrollment_id', 'indicator_id', 'period_id', 'grade'
        ):
            competency_id = indicator_to_competency.get(indicator_id)
            if competency_id:
                competency_period_raw[(enrollment_id, competency_id, period_id)].append(grade)

    grade_record_map = {}
    grade_records = GradeRecord.objects.filter(
        enrollment__in=enrollments,
        course__in=courses,
    )
    if periods:
        grade_records = grade_records.filter(period_id__in=period_name_by_id.keys())
    elif academic_year:
        grade_records = grade_records.filter(period__academic_year=academic_year)
    for enrollment_id, course_id, period_id, grade in grade_records.values_list(
        'enrollment_id', 'course_id', 'period_id', 'grade'
    ):
        grade_record_map[(enrollment_id, course_id, period_id)] = grade

    competency_period_grade = {
        key: calculate_mode_grade(values)
        for key, values in competency_period_raw.items()
    }

    breakdown = {}
    for enrollment in enrollments:
        for course in courses:
            competency_rows = []
            per_period_competency_grades = defaultdict(list)

            for competency_id in competency_ids_by_course.get(course.id, []):
                period_grades = {}
                for period in periods:
                    grade = competency_period_grade.get((enrollment.id, competency_id, period.id))
                    if grade:
                        period_grades[period.id] = grade
                        per_period_competency_grades[period.id].append(grade)

                competency_rows.append({
                    'name': competency_name_by_id.get(competency_id, '-'),
                    'period_grades': period_grades,
                    'final_grade': _mode_from_period_grade_map(period_grades, period_name_by_id),
                })

            period_finals = {}
            for period in periods:
                comp_grades = per_period_competency_grades.get(period.id, [])
                period_finals[period.id] = (
                    calculate_mode_grade(comp_grades)
                    or grade_record_map.get((enrollment.id, course.id, period.id))
                    or '-'
                )

            course_final = _mode_from_period_grade_map(
                {period_id: grade for period_id, grade in period_finals.items() if grade != '-'},
                period_name_by_id,
            )

            breakdown[(enrollment.id, course.id)] = {
                'competencies': competency_rows,
                'period_finals': period_finals,
                'course_final': course_final,
            }

    return periods, breakdown


def _build_grade_section_report(user, grade_id=None, section_id=None):
    is_teacher = user.role == 'teacher' and not user.is_superuser
    active_year = _active_year()

    grades = Grade.objects.order_by('name')
    sections = Section.objects.select_related('grade').order_by('grade__name', 'name')

    assignment_scope = TeacherCourseAssignment.objects.select_related('section__grade', 'grade')
    if active_year:
        assignment_scope = assignment_scope.filter(academic_year=active_year)

    if is_teacher:
        # Only the classroom tutor can view the consolidated report for that section.
        sections = sections.filter(tutor_teacher=user)
        grade_option_ids = list(sections.values_list('grade_id', flat=True).distinct())
        grades = grades.filter(id__in=grade_option_ids) if grade_option_ids else grades.none()

    selected_grade = grades.filter(id=grade_id).first() if grade_id else None
    if not selected_grade:
        selected_grade = grades.first()

    sections_for_grade = sections.filter(grade=selected_grade) if selected_grade else sections.none()
    selected_section = sections_for_grade.filter(id=section_id).first() if section_id else None
    if selected_grade and not selected_section:
        selected_section = sections_for_grade.first()

    rows = []
    courses = Course.objects.none()

    if selected_grade and selected_section:
        enrollments = Enrollment.objects.select_related(
            'student',
            'section__grade',
        ).filter(
            status='active',
            section__grade=selected_grade,
        )
        if active_year:
            enrollments = enrollments.filter(academic_year=active_year)
        enrollments = enrollments.filter(section=selected_section)

        if is_teacher:
            enrollments = enrollments.filter(section=selected_section)

        enrollments = list(
            enrollments.order_by(
                'section__grade__name',
                'section__name',
                'student__last_name',
                'student__first_name',
            )
        )

        section_course_scope = assignment_scope.filter(
            models.Q(section=selected_section)
            | models.Q(section__isnull=True, grade=selected_grade)
        )

        course_ids = list(section_course_scope.values_list('course_id', flat=True).distinct())
        if not course_ids and enrollments:
            course_ids = list(
                GradeRecord.objects.filter(enrollment__in=enrollments).values_list('course_id', flat=True).distinct()
            )
        courses = Course.objects.filter(id__in=course_ids).order_by('name')
        course_list = list(courses)
        _, breakdown = _build_competency_breakdown(enrollments, course_list, active_year)

        for enrollment in enrollments:
            rows.append({
                'enrollment_id': enrollment.id,
                'student': enrollment.student,
                'grade_name': enrollment.section.grade.name,
                'section_name': enrollment.section.name,
                'grades': [
                    breakdown.get((enrollment.id, course.id), {}).get('course_final', '-')
                    for course in course_list
                ],
            })

    return {
        'grades': grades,
        'sections': sections_for_grade,
        'selected_grade': selected_grade,
        'selected_section': selected_section,
        'rows': rows,
        'courses': courses,
        'active_year': active_year,
    }


@role_required('admin', 'director', 'teacher')
def course_report_export_excel(request):
    grade_id = _safe_int(request.GET.get('grade'))
    section_id = _safe_int(request.GET.get('section'))
    report_data = _build_grade_section_report(request.user, grade_id=grade_id, section_id=section_id)
    if request.user.role == 'teacher' and not request.user.is_superuser:
        if not report_data.get('selected_section'):
            messages.error(request, "Solo las tutoras pueden exportar el reporte por grado y seccion.")
            return redirect('teacher_dashboard')

    from openpyxl import Workbook
    from openpyxl.styles import Font

    course_list = list(report_data['courses'])
    enrollment_ids = [row['enrollment_id'] for row in report_data['rows']]
    enrollment_map = {
        enrollment.id: enrollment
        for enrollment in Enrollment.objects.select_related('student', 'section__grade').filter(id__in=enrollment_ids)
    }
    enrollments = [enrollment_map[eid] for eid in enrollment_ids if eid in enrollment_map]
    periods, breakdown = _build_competency_breakdown(enrollments, course_list, report_data['active_year'])

    def _adjust_width(sheet):
        for column_cells in sheet.columns:
            max_length = max(len(str(cell.value or '')) for cell in column_cells)
            sheet.column_dimensions[column_cells[0].column_letter].width = min(max_length + 2, 45)

    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen"

    headers = ['Alumno', 'Grado', 'Seccion'] + [course.name for course in course_list]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in report_data['rows']:
        ws.append([
            str(row['student']),
            row['grade_name'],
            row['section_name'],
            *row['grades'],
        ])

    _adjust_width(ws)

    details_ws = wb.create_sheet(title="Competencias")
    details_headers = ['Alumno', 'Grado', 'Seccion', 'Curso', 'Competencia'] + [period.name for period in periods] + ['Final competencia']
    details_ws.append(details_headers)
    for cell in details_ws[1]:
        cell.font = Font(bold=True)

    for enrollment in enrollments:
        for course in course_list:
            course_data = breakdown.get((enrollment.id, course.id), {})
            competency_rows = course_data.get('competencies', [])
            if not competency_rows:
                details_ws.append([
                    str(enrollment.student),
                    enrollment.section.grade.name,
                    enrollment.section.name,
                    course.name,
                    'Sin competencias',
                    *(('-' for _ in periods)),
                    '-',
                ])
                continue

            for competency_row in competency_rows:
                details_ws.append([
                    str(enrollment.student),
                    enrollment.section.grade.name,
                    enrollment.section.name,
                    course.name,
                    competency_row['name'],
                    *[competency_row['period_grades'].get(period.id, '-') for period in periods],
                    competency_row.get('final_grade', '-') or '-',
                ])
    _adjust_width(details_ws)

    period_ws = wb.create_sheet(title="Finales por periodo")
    period_headers = ['Alumno', 'Grado', 'Seccion', 'Curso'] + [period.name for period in periods] + ['Final curso']
    period_ws.append(period_headers)
    for cell in period_ws[1]:
        cell.font = Font(bold=True)

    for enrollment in enrollments:
        for course in course_list:
            course_data = breakdown.get((enrollment.id, course.id), {})
            period_finals = course_data.get('period_finals', {})
            period_ws.append([
                str(enrollment.student),
                enrollment.section.grade.name,
                enrollment.section.name,
                course.name,
                *[period_finals.get(period.id, '-') for period in periods],
                course_data.get('course_final', '-') or '-',
            ])
    _adjust_width(period_ws)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    grade_slug = report_data['selected_grade'].name.replace(' ', '_') if report_data['selected_grade'] else 'sin_grado'
    section_slug = report_data['selected_section'].name.replace(' ', '_') if report_data['selected_section'] else 'todas_secciones'
    filename = f"reporte_notas_{grade_slug}_{section_slug}.xlsx"

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@role_required('admin', 'director', 'teacher')
def period_report(request):
    periods = Period.objects.select_related('academic_year').order_by('-academic_year__year', 'start_date', 'name')
    selected_period = None
    grades = []
    period_id = request.GET.get('period')
    is_teacher = request.user.role == 'teacher' and not request.user.is_superuser

    if period_id:
        selected_period = get_object_or_404(Period, id=period_id)
        grades_query = GradeRecord.objects.select_related(
            'enrollment__student',
            'course',
            'period'
        ).filter(period=selected_period)
        
        if is_teacher:
            assigned_course_ids = TeacherCourseAssignment.objects.filter(teacher=request.user).values_list('course_id', flat=True)
            grades_query = grades_query.filter(course_id__in=assigned_course_ids)
            
        grades = grades_query

    context = {
        'periods': periods,
        'selected_period': selected_period,
        'grades': grades,
    }
    return render(request, 'academic/period_report.html', context)


@role_required('admin', 'director', 'teacher', 'parent')
def student_report_pdf(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related('student', 'section__grade', 'academic_year__school'),
        id=enrollment_id
    )
    if request.user.role == 'teacher' and not request.user.is_superuser:
        if not _is_section_tutor(request.user, enrollment.section):
            messages.error(request, "Solo la tutora del aula puede exportar la libreta del estudiante.")
            return redirect('teacher_dashboard')
    courses = list(_courses_for_enrollment(request.user, enrollment))
    period_id = _safe_int(request.GET.get('period'))
    preferred_period = _preferred_period(enrollment.academic_year)
    if period_id and enrollment.academic_year_id:
        preferred_period = (
            Period.objects.filter(academic_year=enrollment.academic_year, id=period_id).first()
            or preferred_period
        )
    _, breakdown = _build_competency_breakdown([enrollment], courses, enrollment.academic_year)

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return HttpResponse(
            "No se pudo generar PDF porque falta la libreria 'reportlab'.",
            content_type='text/plain'
        )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        name='ReportTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        alignment=1,  # center
    )
    style_cell = ParagraphStyle(
        name='Cell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.6,
        leading=9.4,
    )
    style_cell_bold = ParagraphStyle(
        name='CellBold',
        parent=style_cell,
        fontName='Helvetica-Bold',
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
        title="Boleta Academica",
    )

    story = []
    school = getattr(enrollment.academic_year, 'school', None) if enrollment.academic_year_id else None
    year_label = str(enrollment.academic_year.year) if enrollment.academic_year_id else ''

    def _maybe_logo(max_w=52, max_h=52):
        if not school or not getattr(school, 'logo', None):
            return None
        try:
            logo_path = school.logo.path
        except Exception:
            return None
        try:
            img_reader = ImageReader(logo_path)
            iw, ih = img_reader.getSize()
        except Exception:
            return None
        if not iw or not ih:
            return None
        scale = min(max_w / float(iw), max_h / float(ih))
        return Image(logo_path, width=iw * scale, height=ih * scale)

    left_logo = _maybe_logo()
    right_logo = _maybe_logo()

    header = Table(
        [[
            left_logo or '',
            Paragraph(f"INFORME DE PROGRESO DE APRENDIZAJE DEL ESTUDIANTE - {year_label}", style_title),
            right_logo or '',
        ]],
        colWidths=[60, doc.width - 120, 60],
    )
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#D9F0FF')),
        ('BOX', (1, 0), (1, 0), 0.8, colors.HexColor('#6AAED6')),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(header)
    story.append(Spacer(1, 8))

    student = enrollment.student
    student_full_name = f"{student.last_name}, {student.first_name}".upper() if student else "-"
    grade_name = str(enrollment.section.grade) if enrollment.section_id else "-"
    section_name = str(enrollment.section.name) if enrollment.section_id else "-"
    school_name = str(school.name) if school else "-"

    info = [
        [Paragraph("NIVEL", style_cell_bold), Paragraph("Primaria", style_cell),
         Paragraph("I.E.", style_cell_bold), Paragraph(school_name, style_cell)],
        [Paragraph("GRADO", style_cell_bold), Paragraph(str(grade_name), style_cell),
         Paragraph("SECCION", style_cell_bold), Paragraph(str(section_name), style_cell)],
        [Paragraph("APELLIDOS Y NOMBRES", style_cell_bold), Paragraph(student_full_name, style_cell_bold), "", ""],
    ]
    info_table = Table(info, colWidths=[90, 150, 90, doc.width - 330])
    info_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.7, colors.black),
        ('BACKGROUND', (0, 0), (-1, 1), colors.HexColor('#D9F0FF')),
        ('SPAN', (1, 2), (-1, 2)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10))

    bimestre_periods = []
    if enrollment.academic_year_id:
        bimestre_periods = [
            p for p in Period.objects.filter(academic_year=enrollment.academic_year).order_by('start_date', 'name')
            if 'bimestre' in (p.name or '').lower()
        ][:4]

    # Map columns I..IV to bimestre periods (if missing, it will show "-").
    period_cols = (bimestre_periods + [None, None, None, None])[:4]

    big_table_data = [
        [
            Paragraph("AREAS", style_cell_bold),
            Paragraph("COMPETENCIAS", style_cell_bold),
            Paragraph("CALIFICATIVO POR BIMESTRE", style_cell_bold),
            "",
            "",
            "",
            Paragraph("PF", style_cell_bold),
        ],
        [
            "",
            "",
            Paragraph("I", style_cell_bold),
            Paragraph("II", style_cell_bold),
            Paragraph("III", style_cell_bold),
            Paragraph("IV", style_cell_bold),
            "",
        ],
    ]

    area_spans = []
    current_row = 2  # after headers

    for course in courses:
        course_data = breakdown.get((enrollment.id, course.id), {}) or {}
        competencies = course_data.get('competencies', []) or []
        if not competencies:
            continue

        start_row = current_row
        for competency_row in competencies:
            period_grades = competency_row.get('period_grades', {}) or {}
            row = [
                Paragraph(str(course.name).upper(), style_cell_bold),
                Paragraph(str(competency_row.get('name', '-') or '-'), style_cell),
            ]
            for period in period_cols:
                if not period:
                    row.append(Paragraph("-", style_cell))
                    continue
                row.append(Paragraph(str(period_grades.get(period.id, '-') or '-'), style_cell_bold))
            row.append(Paragraph(str(competency_row.get('final_grade', '-') or '-'), style_cell_bold))
            big_table_data.append(row)
            current_row += 1

        end_row = current_row - 1
        if end_row > start_row:
            area_spans.append((start_row, end_row))

    col_widths = [
        78,  # areas
        doc.width - (78 + 4 * 36 + 36),  # competencies
        36, 36, 36, 36,  # I-IV
        36,  # PF
    ]
    t = Table(big_table_data, colWidths=col_widths, repeatRows=2)
    table_style_cmds = [
        ('GRID', (0, 0), (-1, -1), 0.7, colors.black),
        ('BACKGROUND', (0, 0), (-1, 1), colors.HexColor('#D9F0FF')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (2, 2), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (-1, 1), 'CENTER'),
        ('SPAN', (0, 0), (0, 1)),
        ('SPAN', (1, 0), (1, 1)),
        ('SPAN', (2, 0), (5, 0)),
        ('SPAN', (6, 0), (6, 1)),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    for start_row, end_row in area_spans:
        table_style_cmds.append(('SPAN', (0, start_row), (0, end_row)))
        table_style_cmds.append(('VALIGN', (0, start_row), (0, end_row), 'MIDDLE'))
        table_style_cmds.append(('ALIGN', (0, start_row), (0, end_row), 'CENTER'))

    t.setStyle(TableStyle(table_style_cmds))
    story.append(t)

    doc.build(story)
    pdf_bytes = buffer.getvalue()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="boleta_{enrollment.id}.pdf"'
    return response


def _calculate_course_grade_from_indicators(enrollment, course, period):
    competencies = Competency.objects.filter(course=course).prefetch_related('indicator_set')
    competency_grades = []
    for competency in competencies:
        indicator_ids = list(competency.indicator_set.values_list('id', flat=True))
        if not indicator_ids:
            continue
        grades = IndicatorGrade.objects.filter(
            enrollment=enrollment,
            period=period,
            indicator_id__in=indicator_ids
        ).values_list('grade', flat=True)
        comp_grade = calculate_mode_grade(list(grades))
        if comp_grade:
            competency_grades.append(comp_grade)

    return calculate_mode_grade(competency_grades)


@role_required('admin', 'director', 'teacher')
def teacher_competency_gradebook(request):
    assignments = TeacherCourseAssignment.objects.select_related(
        'teacher',
        'course',
        'section__grade',
        'academic_year'
    )
    if request.user.role == 'teacher' and not request.user.is_superuser:
        assignments = assignments.filter(teacher=request.user)

    active_year = AcademicYear.objects.filter(is_active=True).first()
    periods = (
        Period.objects.filter(academic_year=active_year).order_by('start_date', 'name')
        if active_year else Period.objects.none()
    )

    assignment_id = request.POST.get('assignment') if request.method == 'POST' else request.GET.get('assignment')
    selected_assignment = assignments.filter(id=assignment_id).first() if assignment_id else None

    selected_period = None
    period_id = request.POST.get('period') if request.method == 'POST' else request.GET.get('period')
    if selected_assignment:
        if active_year != selected_assignment.academic_year:
            periods = Period.objects.filter(
                academic_year=selected_assignment.academic_year
            ).order_by('start_date', 'name')
        selected_period = periods.filter(id=period_id).first() if period_id else None

    competencies = []
    competency_blocks = []
    rows = []
    is_locked = False
    can_edit = True
    can_unlock_lock = False
    lock_next_url = ''

    if selected_assignment and selected_period:
        competencies = list(
            Competency.objects.filter(course=selected_assignment.course).prefetch_related('indicator_set')
        )
        for competency in competencies:
            indicators = list(competency.indicator_set.all())
            competency_blocks.append({'competency': competency, 'indicators': indicators})

        enrollment_filters = {
            'academic_year': selected_assignment.academic_year,
            'status': 'active'
        }
        if selected_assignment.section:
            enrollment_filters['section'] = selected_assignment.section
        elif selected_assignment.grade:
            enrollment_filters['section__grade'] = selected_assignment.grade

        enrollments = Enrollment.objects.select_related('student').filter(
            **enrollment_filters
        ).order_by('student__last_name', 'student__first_name')

        all_indicator_ids = [indicator.id for block in competency_blocks for indicator in block['indicators']]
        score_values = {}
        if all_indicator_ids:
            score_values = {
                f"{score.enrollment_id}_{score.indicator_id}": score.grade
                for score in IndicatorGrade.objects.filter(
                    enrollment__in=enrollments,
                    period=selected_period,
                    indicator_id__in=all_indicator_ids
                )
            }

        lock = GradeSubmissionLock.objects.filter(
            teacher=selected_assignment.teacher,
            course=selected_assignment.course,
            section=selected_assignment.section,
            period=selected_period
        ).first()
        is_locked = lock.is_locked if lock else False
        can_edit = not is_locked
        can_unlock_lock = (
            is_locked and (
                request.user.role in {'admin', 'director'} or request.user.is_superuser
            )
        )
        lock_next_url = f"{request.path}?assignment={selected_assignment.id}&period={selected_period.id}"

        if request.method == 'POST':
            if is_locked:
                if can_unlock_lock:
                    messages.error(request, 'El registro esta bloqueado. Primero habilita la edicion.')
                else:
                    messages.error(request, 'Las notas para esta unidad estan bloqueadas. Contacte al director o admin.')
                return redirect(lock_next_url)

            valid_grades = {'AD', 'A', 'B', 'C'}
            with transaction.atomic():
                existing_records = {
                    (record.enrollment_id, record.indicator_id): record
                    for record in IndicatorGrade.objects.filter(
                        enrollment__in=enrollments,
                        period=selected_period,
                        indicator_id__in=all_indicator_ids
                    )
                }

                for enrollment in enrollments:
                    for block in competency_blocks:
                        for indicator in block['indicators']:
                            field_name = f"score_{enrollment.id}_{indicator.id}"
                            value = request.POST.get(field_name, '').strip().upper()
                            key = (enrollment.id, indicator.id)
                            current = existing_records.get(key)
                            if value in valid_grades:
                                if current:
                                    if current.grade != value:
                                        current.grade = value
                                        current.save(update_fields=['grade'])
                                else:
                                    IndicatorGrade.objects.create(
                                        enrollment=enrollment,
                                        indicator=indicator,
                                        period=selected_period,
                                        grade=value,
                                    )
                            elif current:
                                current.delete()

                for enrollment in enrollments:
                    final_grade = _calculate_course_grade_from_indicators(
                        enrollment, selected_assignment.course, selected_period
                    )
                    if final_grade:
                        GradeRecord.objects.update_or_create(
                            enrollment=enrollment,
                            course=selected_assignment.course,
                            period=selected_period,
                            defaults={'grade': final_grade}
                        )
                    else:
                        GradeRecord.objects.filter(
                            enrollment=enrollment,
                            course=selected_assignment.course,
                            period=selected_period
                        ).delete()

                if request.POST.get('finalize'):
                    lock_obj, _ = GradeSubmissionLock.objects.get_or_create(
                        teacher=selected_assignment.teacher,
                        course=selected_assignment.course,
                        section=selected_assignment.section,
                        period=selected_period
                    )
                    lock_obj.is_locked = True
                    lock_obj.save()
                    messages.success(request, 'Notas finalizadas y bloqueadas.')
                else:
                    messages.success(request, 'Borrador de notas guardado.')

            return redirect(lock_next_url)

        for enrollment in enrollments:
            blocks = []
            competency_grades = []
            for block in competency_blocks:
                cells = []
                indicator_grades = []
                for indicator in block['indicators']:
                    score_key = f"{enrollment.id}_{indicator.id}"
                    value = score_values.get(score_key, '')
                    if value:
                        indicator_grades.append(value)
                    cells.append({
                        'indicator': indicator,
                        'field_name': f"score_{score_key}",
                        'value': value,
                    })
                competency_grade = calculate_mode_grade(indicator_grades) or '-'
                if competency_grade != '-':
                    competency_grades.append(competency_grade)
                blocks.append({
                    'competency': block['competency'],
                    'cells': cells,
                    'competency_grade': competency_grade,
                })

            rows.append({
                'enrollment': enrollment,
                'blocks': blocks,
                'course_grade': calculate_mode_grade(competency_grades) or '-',
            })

    context = {
        'assignments': assignments,
        'selected_assignment': selected_assignment,
        'periods': periods,
        'selected_period': selected_period,
        'competency_blocks': competency_blocks,
        'rows': rows,
        'grade_options': GradeRecord.GRADE_SCALE,
        'has_competencies': bool(competencies),
        'is_locked': is_locked,
        'can_edit': can_edit,
        'can_unlock_lock': can_unlock_lock,
        'lock_next_url': lock_next_url,
    }
    return render(request, 'academic/teacher_gradebook.html', context)


@role_required('admin', 'director', 'teacher')
def manage_competencies(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    
    # Security check: if teacher, must be assigned to this course
    if request.user.role == 'teacher' and not request.user.is_superuser:
        has_assignment = TeacherCourseAssignment.objects.filter(teacher=request.user, course=course).exists()
        if not has_assignment:
            messages.error(request, "No tienes permiso para gestionar este curso.")
            return redirect('teacher_dashboard')

    if request.method == 'POST':
        form = CompetencyForm(request.POST)
        if form.is_valid():
            competency = form.save(commit=False)
            competency.course = course
            last_order = (
                Competency.objects.filter(course=course)
                .aggregate(max_order=models.Max('order'))
                .get('max_order')
                or 0
            )
            competency.order = last_order + 1
            competency.save()
            messages.success(request, f"Competencia '{competency.name}' agregada.")
            return redirect('manage_competencies', course_id=course.id)
    else:
        form = CompetencyForm()

    competencies = Competency.objects.filter(course=course).prefetch_related('indicator_set')
    return render(request, 'academic/manage_competencies.html', {
        'course': course,
        'competencies': competencies,
        'form': form
    })


@role_required('admin', 'director', 'teacher')
def delete_competency(request, competency_id):
    competency = get_object_or_404(Competency, id=competency_id)
    course_id = competency.course_id
    
    # Security check
    if request.user.role == 'teacher' and not request.user.is_superuser:
        has_assignment = TeacherCourseAssignment.objects.filter(teacher=request.user, course=competency.course).exists()
        if not has_assignment:
            return HttpResponse("Unauthorized", status=401)

    competency.delete()
    messages.success(request, "Competencia eliminada.")
    return redirect('manage_competencies', course_id=course_id)


@role_required('admin', 'director', 'teacher')
def manage_indicators(request, competency_id):
    competency = get_object_or_404(Competency, id=competency_id)
    course = competency.course
    
    # Security check
    if request.user.role == 'teacher' and not request.user.is_superuser:
        has_assignment = TeacherCourseAssignment.objects.filter(teacher=request.user, course=course).exists()
        if not has_assignment:
            messages.error(request, "No tienes permiso para gestionar esto.")
            return redirect('teacher_dashboard')

    if request.method == 'POST':
        form = IndicatorForm(request.POST)
        if form.is_valid():
            indicator = form.save(commit=False)
            indicator.competency = competency
            last_order = (
                Indicator.objects.filter(competency=competency)
                .aggregate(max_order=models.Max('order'))
                .get('max_order')
                or 0
            )
            indicator.order = last_order + 1
            indicator.save()
            messages.success(request, f"Indicador '{indicator.name}' agregado.")
            return redirect('manage_indicators', competency_id=competency.id)
    else:
        form = IndicatorForm()

    indicators = Indicator.objects.filter(competency=competency)
    return render(request, 'academic/manage_indicators.html', {
        'competency': competency,
        'course': course,
        'indicators': indicators,
        'form': form
    })


@role_required('admin', 'director', 'teacher')
def delete_indicator(request, indicator_id):
    indicator = get_object_or_404(Indicator, id=indicator_id)
    competency_id = indicator.competency_id
    
    # Security check
    if request.user.role == 'teacher' and not request.user.is_superuser:
        has_assignment = TeacherCourseAssignment.objects.filter(teacher=request.user, course=indicator.competency.course).exists()
        if not has_assignment:
            return HttpResponse("Unauthorized", status=401)

    indicator.delete()
    messages.success(request, "Indicador eliminado.")
    return redirect('manage_indicators', competency_id=competency_id)
@role_required('admin', 'director')
def auto_assign_poly_courses(request):
    from accounts.models import User
    
    # 1. Get all courses marked as poly_course
    poly_courses = Course.objects.filter(is_poly_course=True)
    if not poly_courses.exists():
        messages.warning(request, "No hay cursos marcados como 'Polidocencia'. Por favor, edita los cursos y marca esta opción.")
        return redirect('course_management')

    # 2. Get active academic year
    active_year = AcademicYear.objects.filter(is_active=True).order_by('-year').first()
    if not active_year:
        messages.error(request, "No hay un año académico activo.")
        return redirect('course_management')

    # 3. Get all sections
    sections = Section.objects.select_related('grade').all()
    count = 0
    assigned_info = []
    
    with transaction.atomic():
        for section in sections:
            grade_name = section.grade.name.lower()
            
            for course in poly_courses:
                should_assign = False
                name = course.name
                
                if "ciencia" in name.lower():
                    # Special Rule for Science: 4th to 6th grade
                    is_4_to_6 = any(x in grade_name for x in ["4", "5", "6"])
                    if is_4_to_6:
                        should_assign = True
                else:
                    # Others are for all grades
                    should_assign = True
                
                if should_assign:
                    # Find a teacher linked to this course
                    teacher = User.objects.filter(role='teacher', is_polyteacher=True, poly_course=course).first()
                    
                    if not teacher:
                        # If no poly teacher specifically linked to the FK, check M2M for retrocompat
                        teacher = User.objects.filter(role='teacher', is_polyteacher=True, teaching_courses=course).first()

                    if teacher:
                        obj, created = TeacherCourseAssignment.objects.get_or_create(
                            course=course,
                            section=section,
                            academic_year=active_year,
                            defaults={
                                'grade': section.grade,
                                'teacher': teacher,
                            }
                        )
                        if created:
                            count += 1
                    else:
                        assigned_info.append(f"No se pudo asignar '{name}' a {section} porque no hay un docente polidocente vinculado a este curso.")

    if count > 0:
        messages.success(request, f"Se han creado {count} asignaciones de cursos de polidocencia.")
    
    if assigned_info:
        for info in set(assigned_info): # Use set to avoid repeating same message for every section
            messages.warning(request, info)
            
    if count == 0 and not assigned_info:
        messages.info(request, "No se realizaron nuevas asignaciones. Es posible que ya estén configuradas.")

    return redirect('course_management')
