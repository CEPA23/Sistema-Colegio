from academic.models import Section, TeacherCourseAssignment
from enrollment.models import Enrollment


def teacher_section_ids(user):
    if not user or user.role != 'teacher' or user.is_superuser:
        return []

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


def teacher_tutor_section_ids(user):
    if not user or user.role != 'teacher' or user.is_superuser:
        return []

    tutor_section_ids = Section.objects.filter(
        tutor_teacher=user,
    ).values_list('id', flat=True)
    profile_section_ids = []
    if user.teaching_section_id:
        profile_section_ids.append(user.teaching_section_id)
    profile_section_ids.extend(user.teaching_sections.values_list('id', flat=True))
    return sorted(set(tutor_section_ids).union(profile_section_ids))


def teacher_accessible_enrollments(user, *, include_all_statuses=False):
    enrollments = Enrollment.objects.select_related('student', 'section__grade', 'academic_year')
    if user and user.role == 'teacher' and not user.is_superuser:
        section_ids = teacher_section_ids(user)
        if not section_ids:
            return enrollments.none()
        enrollments = enrollments.filter(section_id__in=section_ids)
        if not include_all_statuses:
            enrollments = enrollments.filter(status='active')
    return enrollments


def teacher_tutor_enrollments(user, *, include_all_statuses=False):
    enrollments = Enrollment.objects.select_related('student', 'section__grade', 'academic_year')
    if user and user.role == 'teacher' and not user.is_superuser:
        section_ids = teacher_tutor_section_ids(user)
        if not section_ids:
            return enrollments.none()
        enrollments = enrollments.filter(section_id__in=section_ids)
        if not include_all_statuses:
            enrollments = enrollments.filter(status='active')
    return enrollments


def teacher_can_access_section(user, section_id):
    if not user or user.role != 'teacher' or user.is_superuser:
        return True
    return section_id in set(teacher_section_ids(user))


def teacher_can_access_enrollment(user, enrollment):
    if not enrollment:
        return False
    return teacher_can_access_section(user, enrollment.section_id)
