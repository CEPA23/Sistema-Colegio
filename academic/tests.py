from io import BytesIO

from django.test import Client, TestCase
from django.urls import reverse

from openpyxl import load_workbook

from accounts.models import User
from enrollment.models import Enrollment
from schools.models import School
from students.models import Student

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
    Unit,
    calculate_mode_grade,
)
from .sync import sync_teacher_course_assignments_for_teacher


class GradeCalculationTests(TestCase):
    def test_competency_average_conversion_for_all_pair_combinations(self):
        expected_results = {
            ('AD', 'AD'): 'AD',
            ('AD', 'A'): 'AD',
            ('AD', 'B'): 'A',
            ('AD', 'C'): 'A',
            ('A', 'A'): 'A',
            ('A', 'B'): 'A',
            ('A', 'C'): 'B',
            ('B', 'B'): 'B',
            ('B', 'C'): 'B',
            ('C', 'C'): 'C',
        }

        for grades, expected in expected_results.items():
            with self.subTest(grades=grades):
                self.assertEqual(calculate_mode_grade(list(grades)), expected)

    def test_competency_average_conversion_for_multiple_values(self):
        cases = [
            (['A', 'C'], 'B'),
            (['A', 'B'], 'A'),
            (['AD', 'AD', 'C', 'C'], 'A'),
            (['B', 'B', 'B', 'B'], 'B'),
            (['AD', 'AD', 'AD', 'C'], 'A'),
            (['AD', 'AD', 'AD', 'AD'], 'AD'),
            (['AD', 'B', 'B', 'C'], 'B'),
            (['A', 'A', 'C', 'C'], 'B'),
        ]

        for grades, expected in cases:
            with self.subTest(grades=grades):
                self.assertEqual(calculate_mode_grade(grades), expected)


class CourseGradeMatrixSyncTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name='Colegio Demo',
            address='Av. Principal 123',
            phone='999999999',
            email='demo@example.com',
        )
        self.active_year = AcademicYear.objects.create(
            school=self.school,
            year=2026,
            is_active=True,
        )
        self.grade = Grade.objects.create(name='3 grado')
        self.section = Section.objects.create(name='A', grade=self.grade)
        self.admin = User.objects.create_user(
            username='admin',
            password='secret123',
            role='admin',
        )
        self.teacher = User.objects.create_user(
            username='docente',
            password='secret123',
            role='teacher',
            teaching_grade=self.grade,
            teaching_section=self.section,
        )
        self.course_math = Course.objects.create(name='Matematica')
        self.course_four = Course.objects.create(name='4')

    def test_matrix_post_syncs_tutor_assignments_when_courses_change(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('course_grade_matrix'),
            data={f'cg_{self.course_math.id}_{self.grade.id}': 'on'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertQuerySetEqual(
            TeacherCourseAssignment.objects.filter(
                teacher=self.teacher,
                academic_year=self.active_year,
            ).order_by('course__name'),
            ['<TeacherCourseAssignment: Matematica | 3 grado A (2026) - docente>'],
            transform=repr,
        )

        response = self.client.post(
            reverse('course_grade_matrix'),
            data={f'cg_{self.course_four.id}_{self.grade.id}': 'on'},
        )
        self.assertEqual(response.status_code, 302)

        assignments = TeacherCourseAssignment.objects.filter(
            teacher=self.teacher,
            academic_year=self.active_year,
        )
        self.assertEqual(assignments.count(), 1)
        assignment = assignments.get()
        self.assertEqual(assignment.course_id, self.course_four.id)
        self.assertEqual(assignment.grade_id, self.grade.id)
        self.assertEqual(assignment.section_id, self.section.id)

    def test_polyteacher_assignments_follow_matrix_for_selected_sections(self):
        course_reference = Course.objects.create(name='Comunicacion')
        course_reference.grades.add(self.grade)

        poly_teacher = User.objects.create_user(
            username='poly',
            password='secret123',
            role='teacher',
            is_polyteacher=True,
        )
        poly_teacher.teaching_courses.add(self.course_four)
        poly_teacher.teaching_sections.add(self.section)

        sync_teacher_course_assignments_for_teacher(
            poly_teacher,
            active_year=self.active_year,
        )
        self.assertFalse(
            TeacherCourseAssignment.objects.filter(
                teacher=poly_teacher,
                academic_year=self.active_year,
                course=self.course_four,
                section=self.section,
            ).exists()
        )

        self.course_four.grades.add(self.grade)
        sync_teacher_course_assignments_for_teacher(
            poly_teacher,
            active_year=self.active_year,
        )
        self.assertTrue(
            TeacherCourseAssignment.objects.filter(
                teacher=poly_teacher,
                academic_year=self.active_year,
                course=self.course_four,
                section=self.section,
            ).exists()
        )

        self.course_four.grades.remove(self.grade)
        sync_teacher_course_assignments_for_teacher(
            poly_teacher,
            active_year=self.active_year,
        )
        self.assertFalse(
            TeacherCourseAssignment.objects.filter(
                teacher=poly_teacher,
                academic_year=self.active_year,
                course=self.course_four,
                section=self.section,
            ).exists()
        )

    def test_polyteacher_gradebook_reuses_competencies_and_labels_sections(self):
        section_b = Section.objects.create(name='B', grade=self.grade)
        english = Course.objects.create(name='Inglés')
        period = Period.objects.create(
            name='Bimestre 1',
            academic_year=self.active_year,
            start_date='2026-03-01',
            end_date='2026-05-31',
            is_active=True,
        )
        poly_teacher = User.objects.create_user(
            username='ingles',
            password='secret123',
            role='teacher',
            is_polyteacher=True,
        )
        source_assignment = TeacherCourseAssignment.objects.create(
            teacher=poly_teacher,
            course=english,
            grade=self.grade,
            section=self.section,
            academic_year=self.active_year,
        )
        target_assignment = TeacherCourseAssignment.objects.create(
            teacher=poly_teacher,
            course=english,
            grade=self.grade,
            section=section_b,
            academic_year=self.active_year,
        )
        unit = Unit.objects.create(
            assignment=source_assignment,
            period=period,
            name='Unidad 1',
            order=1,
        )
        competency = Competency.objects.create(
            assignment=source_assignment,
            name='Se comunica oralmente en inglés',
            order=1,
        )
        Indicator.objects.create(
            competency=competency,
            unit=unit,
            name='Participa en diálogos breves',
            order=1,
        )

        self.client.force_login(poly_teacher)
        response = self.client.get(
            reverse('teacher_competency_gradebook'),
            data={
                'assignment': target_assignment.id,
                'period': period.id,
                'unit': 1,
            },
        )

        self.assertContains(response, 'Inglés - 3 grado A')
        self.assertContains(response, 'Inglés - 3 grado B')
        self.assertContains(response, 'Se comunica oralmente en inglés')
        self.assertContains(response, 'Participa en diálogos breves')
        self.assertEqual(response.context['competency_assignment'], source_assignment)

    def test_teacher_gradebook_export_generates_excel_workbook(self):
        period = Period.objects.create(
            name='Bimestre 1',
            academic_year=self.active_year,
            start_date='2026-03-01',
            end_date='2026-05-31',
            is_active=True,
        )
        assignment = TeacherCourseAssignment.objects.create(
            teacher=self.teacher,
            course=self.course_math,
            grade=self.grade,
            section=self.section,
            academic_year=self.active_year,
        )
        unit = Unit.objects.create(
            assignment=assignment,
            period=period,
            name='Unidad 1',
            order=1,
        )
        competency = Competency.objects.create(
            assignment=assignment,
            name='Resuelve problemas',
            order=1,
        )
        indicator = Indicator.objects.create(
            competency=competency,
            unit=unit,
            name='Aplica estrategias',
            order=1,
        )
        student = Student.objects.create(
            dni='12345678',
            first_name='Ana',
            last_name='Perez',
        )
        enrollment = Enrollment.objects.create(
            student=student,
            academic_year=self.active_year,
            section=self.section,
        )
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse('teacher_competency_gradebook_export_excel'),
            data={
                'assignment': assignment.id,
                'period': period.id,
                'unit': unit.id,
                f'score_{enrollment.id}_{indicator.id}': 'A',
            },
        )

        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(filename=BytesIO(response.content))
        sheet = workbook['Notas']
        self.assertEqual(sheet['A1'].value, 'Colegio Demo')
        self.assertEqual(sheet['A2'].value, 'REGISTRO AUXILIAR')
        self.assertEqual(sheet['C6'].value, 'Aplica estrategias')
        self.assertEqual(sheet['D6'].value, 'PROMEDIO')
        self.assertEqual(sheet['E5'].value, 'NOTA CURSO')
        self.assertEqual(sheet['C7'].value, 'A')

    def test_manage_indicators_can_replicate_previous_unit(self):
        period = Period.objects.create(
            name='Bimestre 1',
            academic_year=self.active_year,
            start_date='2026-03-01',
            end_date='2026-05-31',
            is_active=True,
        )
        assignment = TeacherCourseAssignment.objects.create(
            teacher=self.teacher,
            course=self.course_math,
            grade=self.grade,
            section=self.section,
            academic_year=self.active_year,
        )
        unit_one = Unit.objects.create(
            assignment=assignment,
            period=period,
            name='Unidad 1',
            order=1,
        )
        unit_two = Unit.objects.create(
            assignment=assignment,
            period=period,
            name='Unidad 2',
            order=2,
        )
        competency = Competency.objects.create(
            assignment=assignment,
            name='Resuelve problemas',
            order=1,
        )
        Indicator.objects.create(
            competency=competency,
            unit=unit_one,
            name='Aplica estrategias',
            order=1,
        )

        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse('manage_indicators', args=[competency.id]),
            data={
                'period': period.id,
                'unit': unit_two.id,
                'replicate_previous_unit': '1',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Indicator.objects.filter(
                competency=competency,
                unit=unit_two,
                name='Aplica estrategias',
            ).exists()
        )
