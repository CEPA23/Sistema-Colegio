from datetime import date

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from academic.models import AcademicYear, Grade, Section
from enrollment.models import Enrollment
from schools.models import School
from students.models import Student

from .reporting import build_attendance_report_data


class AttendanceReportTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name='Colegio Demo',
            address='Av. Principal 123',
            phone='999999999',
        )
        self.academic_year = AcademicYear.objects.create(
            school=self.school,
            year=2026,
            is_active=True,
        )
        self.grade = Grade.objects.create(name='1 grado')
        self.section = Section.objects.create(name='A', grade=self.grade)
        self.teacher = User.objects.create_user(
            username='tutora',
            password='secret123',
            role='teacher',
            teaching_grade=self.grade,
            teaching_section=self.section,
        )
        self.admin = User.objects.create_user(
            username='admin',
            password='secret123',
            role='admin',
        )
        self.other_grade = Grade.objects.create(name='2 grado')
        self.other_section = Section.objects.create(name='A', grade=self.other_grade)
        self.other_student = Student.objects.create(
            dni='11112222',
            first_name='Carlos',
            last_name='Ruiz',
        )
        Enrollment.objects.create(
            student=self.other_student,
            academic_year=self.academic_year,
            section=self.other_section,
            status='active',
        )

        self.student_active = Student.objects.create(
            dni='12345678',
            first_name='Ana',
            last_name='Perez',
        )
        self.student_retired = Student.objects.create(
            dni='87654321',
            first_name='Beto',
            last_name='Lopez',
        )
        Enrollment.objects.create(
            student=self.student_active,
            academic_year=self.academic_year,
            section=self.section,
            status='active',
        )
        Enrollment.objects.create(
            student=self.student_retired,
            academic_year=self.academic_year,
            section=self.section,
            status='retired',
        )

    def test_monthly_report_includes_non_active_enrollments_from_section(self):
        report = build_attendance_report_data(self.section, date(2026, 5, 1), request_user=self.teacher)

        self.assertEqual(report['student_count'], 2)
        self.assertEqual(
            [row['student_name'] for row in report['rows']],
            ['Perez, Ana', 'Lopez, Beto'],
        )

    def test_admin_can_open_student_selector_for_any_student(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('attendance_student_report'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ana Perez')
        self.assertContains(response, 'Beto Lopez')
        self.assertContains(response, 'Carlos Ruiz')

    def test_teacher_only_sees_students_from_own_section_in_selector(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('attendance_student_report'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ana Perez')
        self.assertContains(response, 'Beto Lopez')
        self.assertNotContains(response, 'Carlos Ruiz')
