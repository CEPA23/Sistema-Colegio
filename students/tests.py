from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from academic.models import AcademicYear, Grade, Section
from enrollment.models import Enrollment
from schools.models import School
from students.models import Student


class TeacherStudentScopeTests(TestCase):
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
        self.section_a = Section.objects.create(name='A', grade=self.grade)
        self.section_b = Section.objects.create(name='B', grade=self.grade)
        self.teacher = User.objects.create_user(
            username='tutora',
            password='secret123',
            role='teacher',
            teaching_grade=self.grade,
            teaching_section=self.section_a,
        )
        self.student_a = Student.objects.create(
            dni='12345678',
            first_name='Ana',
            last_name='Perez',
        )
        self.student_b = Student.objects.create(
            dni='87654321',
            first_name='Beto',
            last_name='Lopez',
        )
        Enrollment.objects.create(
            student=self.student_a,
            academic_year=self.academic_year,
            section=self.section_a,
            status='active',
        )
        Enrollment.objects.create(
            student=self.student_b,
            academic_year=self.academic_year,
            section=self.section_b,
            status='active',
        )

    def test_teacher_only_sees_students_from_assigned_section(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('student_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ana Perez')
        self.assertNotContains(response, 'Beto Lopez')

    def test_teacher_cannot_open_student_profile_outside_assigned_section(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('student_profile', args=[self.student_b.id]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('student_list'))
