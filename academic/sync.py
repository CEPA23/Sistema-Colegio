from django.db import transaction

from .models import AcademicYear, Course, TeacherCourseAssignment


def _active_year():
    return AcademicYear.objects.filter(is_active=True).order_by('-year').first()


def _course_grade_map():
    course_grade_ids = {}
    grade_has_matrix = set()

    for course in Course.objects.prefetch_related('grades').all():
        grade_ids = set(course.grades.values_list('id', flat=True))
        course_grade_ids[course.id] = grade_ids
        grade_has_matrix.update(grade_ids)

    return course_grade_ids, grade_has_matrix


def _allowed_course_ids_for_grade(grade_id, course_grade_ids, grade_has_matrix):
    if grade_id in grade_has_matrix:
        return {
            course_id
            for course_id, allowed_grade_ids in course_grade_ids.items()
            if grade_id in allowed_grade_ids
        }

    # Preserve the old behavior for grades that have not been configured yet.
    return set(course_grade_ids.keys())


def sync_teacher_course_assignments_for_teacher(
    teacher,
    *,
    active_year=None,
    extra_section_ids=None,
    course_grade_ids=None,
    grade_has_matrix=None,
):
    if active_year is None:
        active_year = _active_year()
    if not active_year or not teacher:
        return

    if teacher.role != 'teacher':
        TeacherCourseAssignment.objects.filter(
            teacher=teacher,
            academic_year=active_year,
        ).delete()
        return

    if course_grade_ids is None or grade_has_matrix is None:
        course_grade_ids, grade_has_matrix = _course_grade_map()

    sections_by_id = {}
    if teacher.teaching_section_id and teacher.teaching_section:
        sections_by_id[teacher.teaching_section_id] = teacher.teaching_section

    if teacher.is_polyteacher:
        for section in teacher.teaching_sections.select_related('grade').all():
            sections_by_id[section.id] = section

    section_ids_to_touch = set(sections_by_id.keys())
    section_ids_to_touch.update(
        section_id for section_id in (extra_section_ids or []) if section_id
    )

    existing_assignments = {
        (assignment.course_id, assignment.section_id): assignment
        for assignment in TeacherCourseAssignment.objects.filter(
            teacher=teacher,
            academic_year=active_year,
            section_id__in=section_ids_to_touch,
        )
    }

    expected_assignments = {}

    if teacher.teaching_section_id and teacher.teaching_section:
        section = teacher.teaching_section
        for course_id in _allowed_course_ids_for_grade(
            section.grade_id,
            course_grade_ids,
            grade_has_matrix,
        ):
            expected_assignments[(course_id, section.id)] = section.grade_id

    if teacher.is_polyteacher:
        selected_course_ids = set(teacher.teaching_courses.values_list('id', flat=True))
        for section in teacher.teaching_sections.select_related('grade').all():
            allowed_course_ids = _allowed_course_ids_for_grade(
                section.grade_id,
                course_grade_ids,
                grade_has_matrix,
            )
            for course_id in selected_course_ids.intersection(allowed_course_ids):
                expected_assignments[(course_id, section.id)] = section.grade_id

    with transaction.atomic():
        stale_assignment_ids = [
            assignment.id
            for key, assignment in existing_assignments.items()
            if key not in expected_assignments
        ]
        if stale_assignment_ids:
            TeacherCourseAssignment.objects.filter(id__in=stale_assignment_ids).delete()

        for (course_id, section_id), grade_id in expected_assignments.items():
            assignment = existing_assignments.get((course_id, section_id))
            if assignment:
                if assignment.grade_id != grade_id:
                    assignment.grade_id = grade_id
                    assignment.save(update_fields=['grade'])
                continue

            TeacherCourseAssignment.objects.create(
                teacher=teacher,
                course_id=course_id,
                grade_id=grade_id,
                section_id=section_id,
                academic_year=active_year,
            )


def sync_teacher_course_assignments(*, teacher_ids=None, active_year=None, extra_section_ids_by_teacher=None):
    from accounts.models import User

    if active_year is None:
        active_year = _active_year()
    if not active_year:
        return

    extra_section_ids_by_teacher = extra_section_ids_by_teacher or {}

    teachers = User.objects.filter(role='teacher')
    if teacher_ids:
        teachers = teachers.filter(id__in=teacher_ids)

    teachers = teachers.select_related('teaching_section__grade').prefetch_related(
        'teaching_courses',
        'teaching_sections__grade',
    )

    course_grade_ids, grade_has_matrix = _course_grade_map()

    for teacher in teachers:
        sync_teacher_course_assignments_for_teacher(
            teacher,
            active_year=active_year,
            extra_section_ids=extra_section_ids_by_teacher.get(teacher.id),
            course_grade_ids=course_grade_ids,
            grade_has_matrix=grade_has_matrix,
        )
