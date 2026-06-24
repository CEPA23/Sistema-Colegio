from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.db.models import Sum

from academic.models import AcademicYear, Grade, Section
from enrollment.models import Enrollment
from schools.models import School
from students.models import Student

from .models import Fee, Payment


class MultiMonthPaymentTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name='Colegio Demo',
            address='Calle Demo 123',
            phone='999999999',
            email='demo@example.com',
            pension_price=Decimal('200.00'),
            enrollment_price=Decimal('300.00'),
            supplies_price=Decimal('50.00'),
        )
        self.academic_year = AcademicYear.objects.create(
            school=self.school,
            year=2026,
            is_active=True,
        )
        self.grade = Grade.objects.create(name='1er Grado')
        self.section = Section.objects.create(name='A', grade=self.grade)
        self.student = Student.objects.create(
            dni='12345678',
            first_name='Juan',
            last_name='Perez',
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            academic_year=self.academic_year,
            section=self.section,
        )
        self.user = get_user_model().objects.create_user(
            username='secretaria',
            password='pass12345',
            role='secretary',
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_can_pay_multiple_pension_months_in_one_submit(self):
        response = self.client.post(
            reverse('payment_create'),
            {
                'student_name': str(self.student),
                'enrollment_id': self.enrollment.id,
                'concept': Fee.CONCEPT_PENSION,
                'pension_price': '200.00',
                'pension_months': ['1', '2', '3', '4'],
                'amount': '800.00',
                'method': Payment.METHOD_CASH,
                'comment': 'Pago de varios meses',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Payment.objects.count(), 4)
        self.assertEqual(Payment.objects.aggregate(total=Sum('amount'))['total'], Decimal('800.00'))

        paid_fees = Fee.objects.filter(
            enrollment=self.enrollment,
            concept=Fee.CONCEPT_PENSION,
            pension_month__in=[1, 2, 3, 4],
        ).order_by('pension_month')

        self.assertEqual(paid_fees.count(), 4)
        self.assertEqual(sum((fee.amount_paid for fee in paid_fees), Decimal('0.00')), Decimal('800.00'))
        self.assertTrue(all(fee.status == 'paid' for fee in paid_fees))

        payment_ids = list(Payment.objects.order_by('id').values_list('id', flat=True))
        receipt_url = reverse('payment_receipt_pdf', args=[payment_ids[0]]) + f"?payment_ids={','.join(str(pid) for pid in payment_ids)}"
        receipt_response = self.client.get(receipt_url)
        self.assertEqual(receipt_response.status_code, 200)
        self.assertEqual(receipt_response['Content-Type'], 'application/pdf')

    def test_can_override_pension_price_for_special_student(self):
        response = self.client.post(
            reverse('payment_create'),
            {
                'student_name': str(self.student),
                'enrollment_id': self.enrollment.id,
                'concept': Fee.CONCEPT_PENSION,
                'pension_price': '150.00',
                'pension_months': ['1', '2'],
                'amount': '300.00',
                'method': Payment.METHOD_CASH,
                'comment': 'Tarifa especial',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Payment.objects.count(), 2)
        self.assertEqual(Payment.objects.aggregate(total=Sum('amount'))['total'], Decimal('300.00'))

        paid_fees = Fee.objects.filter(
            enrollment=self.enrollment,
            concept=Fee.CONCEPT_PENSION,
            pension_month__in=[1, 2],
        ).order_by('pension_month')

        self.assertEqual(sum((fee.amount_paid for fee in paid_fees), Decimal('0.00')), Decimal('300.00'))
        self.assertTrue(all(fee.amount == Decimal('150.00') for fee in paid_fees))

    def test_payment_history_search_filters_by_student_name(self):
        other_student = Student.objects.create(
            dni='87654321',
            first_name='Maria',
            last_name='Lopez',
        )
        other_enrollment = Enrollment.objects.create(
            student=other_student,
            academic_year=self.academic_year,
            section=self.section,
        )
        Fee.objects.create(
            enrollment=other_enrollment,
            concept=Fee.CONCEPT_ENROLLMENT,
            amount=Decimal('300.00'),
            due_date=self.enrollment.enrolled_at.date(),
        )
        Payment.objects.create(
            fee=Fee.objects.create(
                enrollment=other_enrollment,
                concept=Fee.CONCEPT_PENSION,
                pension_month=1,
                amount=Decimal('200.00'),
                due_date=self.enrollment.enrolled_at.date(),
            ),
            amount=Decimal('200.00'),
            method=Payment.METHOD_CASH,
        )

        response = self.client.get(reverse('payment_history'), {'q': 'Maria'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Maria Lopez')
        self.assertNotContains(response, 'Juan Perez', status_code=200)
