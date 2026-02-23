from io import BytesIO

from django.contrib import messages
from django.db import models, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from enrollment.models import Enrollment

from .forms import CompetencyForm, CourseForm, GradeForm, GradeRecordForm, IndicatorForm, SectionForm, TeacherCourseAssignmentForm
from .models import (
    AcademicYear,
    Competency,
    Course,
    Grade,
    GradeRecord,
    Indicator,
    IndicatorGrade,
    Level,
    Period,
    Section,
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
    edit_course = None
    edit_id = request.GET.get('edit_course')
    if edit_id:
        edit_course = get_object_or_404(Course, id=edit_id)

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'course':
            course_form = CourseForm(request.POST, instance=edit_course)
            assignment_form = TeacherCourseAssignmentForm()
            if course_form.is_valid():
                course = course_form.save()
                if edit_course:
                    messages.success(request, f"Curso '{course.name}' actualizado.")
                else:
                    messages.success(request, f"Curso '{course.name}' creado correctamente.")
                return redirect('course_management')
        else:
            course_form = CourseForm(instance=edit_course)
            assignment_form = TeacherCourseAssignmentForm(request.POST)
            if assignment_form.is_valid():
                assignment = assignment_form.save()
                target_desc = ""
                if assignment.section:
                    target_desc = f"{assignment.section.grade} / {assignment.section}"
                elif assignment.grade:
                    target_desc = f"{assignment.grade}"
                else:
                    target_desc = str(assignment.level or "Nivel desconocido")

                messages.success(
                    request,
                    f"Curso '{assignment.course.name}' asignado a {target_desc}."
                )
                return redirect('course_management')
    else:
        course_form = CourseForm(instance=edit_course)
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
        'edit_course': edit_course,
    }
    return render(request, 'academic/course_management.html', context)


@role_required('admin', 'director', 'secretary')
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

    grades = Grade.objects.select_related('level').order_by('level__name', 'name')
    return render(request, 'academic/grade_management.html', {
        'form': form,
        'grades': grades,
        'edit_grade': edit_grade,
    })


@role_required('admin', 'director', 'secretary')
def section_management(request):
    edit_section = None
    edit_id = request.GET.get('edit_section')
    if edit_id:
        edit_section = get_object_or_404(Section, id=edit_id)

    if request.method == 'POST':
        form = SectionForm(request.POST, instance=edit_section)
        if form.is_valid():
            section = form.save()
            if edit_section:
                messages.success(request, f"Sección '{section.name}' actualizada.")
            else:
                messages.success(request, f"Sección '{section.name}' creada para '{section.grade.name}'.")
            return redirect('section_management')
    else:
        form = SectionForm(instance=edit_section)

    sections = Section.objects.select_related('grade__level').order_by('grade__level__name', 'grade__name', 'name')
    return render(request, 'academic/section_management.html', {
        'form': form,
        'sections': sections,
        'edit_section': edit_section,
    })


@role_required('admin', 'director', 'teacher', 'secretary')
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


@role_required('admin', 'director', 'teacher', 'secretary')
def report_card(request):
    is_teacher = request.user.role == 'teacher' and not request.user.is_superuser
    
    if is_teacher:
        # Filter everything to only what the teacher is assigned to
        assignments = TeacherCourseAssignment.objects.filter(teacher=request.user)
        assigned_course_ids = assignments.values_list('course_id', flat=True)
        
        # Build Section filter
        from academic.models import Section
        q_sections = models.Q(id__in=[]) # Start with empty
        for a in assignments:
            if a.section_id:
                q_sections |= models.Q(id=a.section_id)
            elif a.grade_id:
                q_sections |= models.Q(grade_id=a.grade_id)
            elif a.level_id:
                q_sections |= models.Q(grade__level_id=a.level_id)
        
        relevant_section_ids = Section.objects.filter(q_sections).values_list('id', flat=True)
        
        # We only show students from sections the teacher handles
        enrollments = Enrollment.objects.filter(section_id__in=relevant_section_ids).select_related('student')
        courses = Course.objects.filter(id__in=assigned_course_ids)
    else:
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
    is_teacher = request.user.role == 'teacher' and not request.user.is_superuser
    
    if is_teacher:
        assigned_course_ids = TeacherCourseAssignment.objects.filter(teacher=request.user).values_list('course_id', flat=True)
        courses = Course.objects.filter(id__in=assigned_course_ids)
    else:
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
    is_teacher = request.user.role == 'teacher' and not request.user.is_superuser
    
    if is_teacher:
        assigned_course_ids = TeacherCourseAssignment.objects.filter(teacher=request.user).values_list('course_id', flat=True)
        courses = courses.filter(id__in=assigned_course_ids)

    selected_course = None
    rows = []
    course_id = request.GET.get('course')

    if course_id:
        selected_course = get_object_or_404(courses, id=course_id)
        # Filter enrollments by where this teacher actually teaches this course
        if is_teacher:
            from academic.models import Section
            teacher_course_assignments = TeacherCourseAssignment.objects.filter(
                teacher=request.user, course=selected_course
            )
            q_sections = models.Q(id__in=[])
            for a in teacher_course_assignments:
                if a.section_id:
                    q_sections |= models.Q(id=a.section_id)
                elif a.grade_id:
                    q_sections |= models.Q(grade_id=a.grade_id)
                elif a.level_id:
                    q_sections |= models.Q(grade__level_id=a.level_id)
            
            relevant_section_ids = Section.objects.filter(q_sections).values_list('id', flat=True)
            enrollments = Enrollment.objects.filter(section_id__in=relevant_section_ids).select_related('student')
        else:
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


@role_required('admin', 'director', 'teacher', 'secretary', 'parent')
def student_report_pdf(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related('student', 'section__grade', 'academic_year'),
        id=enrollment_id
    )
    is_teacher = request.user.role == 'teacher' and not request.user.is_superuser
    
    if is_teacher:
        assigned_course_ids = TeacherCourseAssignment.objects.filter(teacher=request.user).values_list('course_id', flat=True)
        courses = Course.objects.filter(id__in=assigned_course_ids)
    else:
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

    # Load periods for the active academic year by default
    active_year = AcademicYear.objects.filter(is_active=True).first()
    periods = Period.objects.filter(academic_year=active_year).order_by('start_date', 'name') if active_year else Period.objects.none()
    
    assignment_id = request.POST.get('assignment') if request.method == 'POST' else request.GET.get('assignment')
    selected_assignment = assignments.filter(id=assignment_id).first() if assignment_id else None

    selected_period = None
    period_id = request.POST.get('period') if request.method == 'POST' else request.GET.get('period')

    if selected_assignment:
        # If assignment has a different year than active, override periods
        if active_year != selected_assignment.academic_year:
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

        enrollment_filters = {
            'academic_year': selected_assignment.academic_year,
            'status': 'active'
        }
        if selected_assignment.section:
            enrollment_filters['section'] = selected_assignment.section
        elif selected_assignment.grade:
            enrollment_filters['section__grade'] = selected_assignment.grade
        elif selected_assignment.level:
            enrollment_filters['section__grade__level'] = selected_assignment.level

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
