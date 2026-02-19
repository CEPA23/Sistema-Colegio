from io import BytesIO

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from enrollment.models import Enrollment

from .forms import CourseForm, GradeRecordForm, TeacherCourseAssignmentForm
from .models import (
    Competency,
    Course,
    GradeRecord,
    IndicatorGrade,
    Period,
    TeacherCourseAssignment,
    calculate_mode_grade,
)


@role_required('admin', 'director', 'teacher', 'secretary')
def academic_dashboard(request):
    context = {
        'total_courses': Course.objects.count(),
        'total_grade_records': GradeRecord.objects.count(),
        'total_periods': Period.objects.count(),
        'total_assignments': TeacherCourseAssignment.objects.count(),
    }
    return render(request, 'academic/academic_dashboard.html', context)


@role_required('admin', 'director', 'secretary')
def course_management(request):
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'course':
            course_form = CourseForm(request.POST)
            assignment_form = TeacherCourseAssignmentForm()
            if course_form.is_valid():
                course = course_form.save()
                messages.success(request, f"Curso '{course.name}' creado correctamente.")
                return redirect('course_management')
        else:
            course_form = CourseForm()
            assignment_form = TeacherCourseAssignmentForm(request.POST)
            if assignment_form.is_valid():
                assignment = assignment_form.save()
                messages.success(
                    request,
                    (
                        f"Curso '{assignment.course.name}' asignado a "
                        f"{assignment.level or assignment.section.grade} / "
                        f"{assignment.section.name}."
                    )
                )
                return redirect('course_management')
    else:
        course_form = CourseForm()
        assignment_form = TeacherCourseAssignmentForm()

    courses = Course.objects.order_by('name')
    assignments = TeacherCourseAssignment.objects.select_related(
        'teacher',
        'course',
        'level',
        'grade',
        'section__grade',
        'academic_year',
    ).order_by(
        '-academic_year__year',
        'level__name',
        'grade__name',
        'section__name',
        'course__name',
    )
    context = {
        'course_form': course_form,
        'assignment_form': assignment_form,
        'courses': courses,
        'assignments': assignments,
    }
    return render(request, 'academic/course_management.html', context)


@role_required('admin', 'director', 'teacher', 'secretary')
def grade_list(request):
    grades = GradeRecord.objects.select_related(
        'enrollment__student',
        'course',
        'period'
    ).order_by('enrollment__student__last_name', 'course__name', 'period__name')

    return render(request, 'academic/grade_list.html', {
        'grades': grades
    })


@role_required('admin', 'director', 'teacher')
def grade_create(request):
    if request.method == 'POST':
        form = GradeRecordForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('grade_list')
    else:
        form = GradeRecordForm()

    return render(request, 'academic/grade_form.html', {
        'form': form
    })


@role_required('admin', 'director', 'teacher', 'secretary')
def report_card(request):
    enrollments = Enrollment.objects.select_related('student')
    courses = Course.objects.all()
    report = []

    for enrollment in enrollments:
        student_data = {
            "student": enrollment.student,
            "enrollment_id": enrollment.id,
            "grades": []
        }
        for course in courses:
            final_grade = GradeRecord.get_final_grade(enrollment, course)
            student_data["grades"].append({
                "course": course.name,
                "final_grade": final_grade or "-"
            })
        report.append(student_data)

    return render(request, 'academic/report_card.html', {
        'report': report,
        'courses': courses
    })


@role_required('admin', 'director', 'teacher', 'secretary', 'parent')
def student_report(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related('student', 'section__grade', 'academic_year'),
        id=enrollment_id
    )
    courses = Course.objects.all()
    grades = []

    for course in courses:
        final_grade = GradeRecord.get_final_grade(enrollment, course)
        grades.append({
            "course": course.name,
            "final_grade": final_grade or "-"
        })

    return render(request, 'academic/student_report.html', {
        'enrollment': enrollment,
        'grades': grades
    })


@role_required('admin', 'director', 'teacher', 'secretary')
def course_report(request):
    courses = Course.objects.all().order_by('name')
    selected_course = None
    rows = []
    course_id = request.GET.get('course')

    if course_id:
        selected_course = get_object_or_404(Course, id=course_id)
        enrollments = Enrollment.objects.select_related('student')
        for enrollment in enrollments:
            rows.append({
                'student': enrollment.student,
                'enrollment_id': enrollment.id,
                'final_grade': GradeRecord.get_final_grade(enrollment, selected_course) or '-'
            })

    context = {
        'courses': courses,
        'selected_course': selected_course,
        'rows': rows,
    }
    return render(request, 'academic/course_report.html', context)


@role_required('admin', 'director', 'teacher', 'secretary')
def period_report(request):
    periods = Period.objects.select_related('academic_year').order_by('-academic_year__year', 'start_date', 'name')
    selected_period = None
    grades = []
    period_id = request.GET.get('period')

    if period_id:
        selected_period = get_object_or_404(Period, id=period_id)
        grades = GradeRecord.objects.select_related(
            'enrollment__student',
            'course',
            'period'
        ).filter(period=selected_period)

    context = {
        'periods': periods,
        'selected_period': selected_period,
        'grades': grades,
    }
    return render(request, 'academic/period_report.html', context)


@role_required('admin', 'director', 'teacher', 'secretary', 'parent')
def student_report_pdf(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related('student', 'section__grade', 'academic_year'),
        id=enrollment_id
    )
    courses = Course.objects.all()
    grades = [(course.name, GradeRecord.get_final_grade(enrollment, course) or '-') for course in courses]

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
        return HttpResponse(
            "No se pudo generar PDF porque falta la libreria 'reportlab'.",
            content_type='text/plain'
        )

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, height - 40, "Boleta Academica")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, height - 65, f"Alumno: {enrollment.student}")
    pdf.drawString(40, height - 82, f"Anio: {enrollment.academic_year.year}")
    pdf.drawString(40, height - 99, f"Seccion: {enrollment.section}")

    y = height - 130
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, "Curso")
    pdf.drawString(300, y, "Nota Final")
    y -= 18
    pdf.setFont("Helvetica", 10)

    for course_name, final_grade in grades:
        if y < 70:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 10)
        pdf.drawString(40, y, course_name)
        pdf.drawString(300, y, str(final_grade))
        y -= 16

    pdf.save()
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
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

    assignment_id = request.POST.get('assignment') if request.method == 'POST' else request.GET.get('assignment')
    selected_assignment = assignments.filter(id=assignment_id).first() if assignment_id else None

    periods = Period.objects.none()
    selected_period = None
    period_id = request.POST.get('period') if request.method == 'POST' else request.GET.get('period')

    if selected_assignment:
        periods = Period.objects.filter(academic_year=selected_assignment.academic_year).order_by('start_date', 'name')
        selected_period = periods.filter(id=period_id).first() if period_id else None

    competencies = []
    competency_blocks = []
    rows = []

    if selected_assignment and selected_period:
        competencies = list(
            Competency.objects.filter(course=selected_assignment.course).prefetch_related('indicator_set')
        )
        competency_blocks = []
        for competency in competencies:
            indicators = list(competency.indicator_set.all())
            competency_blocks.append({'competency': competency, 'indicators': indicators})

        enrollments = Enrollment.objects.select_related('student').filter(
            academic_year=selected_assignment.academic_year,
            section=selected_assignment.section,
            status='active'
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

        if request.method == 'POST':
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
                        enrollment,
                        selected_assignment.course,
                        selected_period
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

            messages.success(request, "Notas por indicadores guardadas correctamente.")
            return redirect(
                f"{request.path}?assignment={selected_assignment.id}&period={selected_period.id}"
            )

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
    }
    return render(request, 'academic/teacher_gradebook.html', context)
