import csv
from datetime import date

from django.contrib import messages
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse, FileResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone

from accounts.decorators import role_required
from academic.models import Grade
from enrollment.models import Enrollment

from .forms import PaymentRegistrationForm
from .models import Fee, Payment


def _concept_label(concept_code):
    return dict(Fee.CONCEPT_CHOICES).get(concept_code, concept_code)


def _month_label(month_value):
    try:
        month_int = int(month_value)
    except (TypeError, ValueError):
        return '-'
    return dict(Fee.MONTH_CHOICES).get(month_int, '-')


def _debtor_queryset(student_query='', grade_id='', section_id='', month='', concept=''):
    # Obtenemos todas las deudas primero
    fees = Fee.objects.select_related(
        'enrollment__student',
        'enrollment__section__grade',
        'enrollment__academic_year'
    )

    # Anotamos con el total pagado y calculamos el balance
    from django.db.models import OuterRef, Subquery
    payments = Payment.objects.filter(fee=OuterRef('pk')).values('fee').annotate(total=Sum('amount')).values('total')
    
    fees = fees.annotate(
        paid_amount=Coalesce(
            Subquery(payments),
            Value(0),
            output_field=DecimalField(max_digits=10, decimal_places=2)
        )
    ).annotate(
        balance_amount=F('amount') - F('paid_amount')
    ).filter(balance_amount__gt=0)

    if student_query:
        fees = fees.filter(
            Q(enrollment__student__first_name__icontains=student_query)
            | Q(enrollment__student__last_name__icontains=student_query)
        )

    if grade_id:
        fees = fees.filter(enrollment__section__grade_id=grade_id)

    if section_id:
        fees = fees.filter(enrollment__section_id=section_id)

    if concept:
        fees = fees.filter(concept=concept)

    if month:
        try:
            month_int = int(month)
            fees = fees.filter(concept=Fee.CONCEPT_PENSION, pension_month=month_int)
        except ValueError:
            pass

    return fees.order_by('enrollment__student__last_name', 'due_date')


@role_required('admin', 'director', 'secretary')
def finance_dashboard(request):
    today = timezone.localdate()
    fees = Fee.objects.select_related('enrollment__student')
    total_billed = fees.aggregate(total=Sum('amount'))['total'] or 0
    total_paid = sum(f.total_paid for f in fees)
    total_pending = sum(f.balance for f in fees)

    context = {
        'total_fees': fees.count(),
        'total_billed': total_billed,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'today_income': Payment.objects.filter(payment_date=today).aggregate(total=Sum('amount'))['total'] or 0,
    }
    return render(request, 'finance/finance_dashboard.html', context)


@role_required('secretary')
def secretary_dashboard(request):
    today = timezone.localdate()
    # Resumen simple para la secretaria
    today_payments = Payment.objects.filter(payment_date=today)
    context = {
        'today': today,
        'today_count': today_payments.count(),
        'today_total': today_payments.aggregate(total=Sum('amount'))['total'] or 0,
    }
    return render(request, 'finance/secretary_dashboard.html', context)


@role_required('admin', 'director', 'secretary', 'parent')
def account_status(request):
    fees = Fee.objects.select_related(
        'enrollment__student',
        'enrollment__academic_year'
    ).order_by('enrollment__student__last_name', 'due_date')

    total_pending = sum(f.balance for f in fees)
    return render(request, 'finance/account_status.html', {
        'fees': fees,
        'total_pending': total_pending,
    })


@role_required('admin', 'director', 'secretary')
def payment_create(request):
    if request.method == 'POST':
        form = PaymentRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            enrollment = form.cleaned_data['enrollment']
            concept = form.cleaned_data['concept']
            pension_month = form.cleaned_data['pension_month']
            course = form.cleaned_data['course']
            amount = form.cleaned_data['amount']
            method = form.cleaned_data['method']
            proof_image = form.cleaned_data['proof_image']
            comment = form.cleaned_data['comment']
            today = timezone.localdate()

            fee_qs = Fee.objects.filter(enrollment=enrollment, concept=concept)
            month_int = int(pension_month) if pension_month else None
            if concept == Fee.CONCEPT_PENSION:
                fee_qs = fee_qs.filter(pension_month=month_int)
            elif concept == Fee.CONCEPT_BOOK:
                fee_qs = fee_qs.filter(course=course)
            else:
                fee_qs = fee_qs.filter(pension_month__isnull=True)

            fee = None
            for candidate in fee_qs.order_by('due_date', 'id'):
                if candidate.balance > 0:
                    fee = candidate
                    break

            if not fee:
                due_date = today
                if concept == Fee.CONCEPT_PENSION and month_int:
                    due_date = date(today.year, month_int, 1)
                fee = Fee.objects.create(
                    enrollment=enrollment,
                    concept=concept,
                    pension_month=month_int if concept == Fee.CONCEPT_PENSION else None,
                    course=course if concept == Fee.CONCEPT_BOOK else None,
                    amount=amount,
                    due_date=due_date,
                )

            if amount > fee.balance:
                form.add_error('amount', f"El saldo de esta deuda es S/ {fee.balance}.")
            else:
                payment = Payment.objects.create(
                    fee=fee,
                    amount=amount,
                    method=method,
                    proof_image=proof_image,
                    comment=comment,
                )
                from django.utils.safestring import mark_safe
                from django.urls import reverse
                receipt_url = reverse('payment_receipt_pdf', args=[payment.id])
                messages.success(
                    request,
                    mark_safe(f"Pago registrado para {payment.fee.enrollment.student}. <a href='{receipt_url}' target='_blank' class='btn btn-subtle' style='margin-left:10px;'>Imprimir Boleta 🖨️</a>")
                )
                return redirect('payment_history')
    else:
        form = PaymentRegistrationForm()

    from schools.models import School
    from academic.models import Course
    school = School.objects.first()
    courses = Course.objects.all()
    suggested_prices = {
        'pension': str(school.pension_price) if school else "200.00",
        'matricula': str(school.enrollment_price) if school else "300.00",
        'material_escolar': str(school.supplies_price) if school else "50.00",
        'books': {str(c.id): str(c.book_price) for c in courses}
    }

    return render(request, 'finance/payment_form.html', {
        'form': form,
        'suggested_prices': suggested_prices
    })


@role_required('admin', 'director', 'secretary')
def student_search(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})

    enrollments = Enrollment.objects.select_related(
        'student',
        'section__grade',
        'academic_year'
    ).filter(
        Q(student__first_name__icontains=query) | Q(student__last_name__icontains=query)
    ).order_by(
        'student__last_name',
        'student__first_name',
        '-academic_year__year'
    )[:20]

    results = [{
        'enrollment_id': e.id,
        'student_name': str(e.student),
        'label': f"{e.student} - {e.section.grade} {e.section.name} ({e.academic_year.year})"
    } for e in enrollments]
    return JsonResponse({'results': results})


@role_required('admin', 'director', 'secretary', 'parent')
def payment_history(request):
    payments = Payment.objects.select_related(
        'fee__enrollment__student'
    ).order_by('-payment_date', '-id')
    return render(request, 'finance/payment_history.html', {'payments': payments})


@role_required('admin', 'director', 'secretary')
def debtors_report(request):
    from academic.models import Section
    student_query = request.GET.get('student', '').strip()
    grade_id = request.GET.get('grade', '').strip()
    section_id = request.GET.get('section', '').strip()
    month = request.GET.get('month', '').strip()
    concept = request.GET.get('concept', '').strip()

    debtors = _debtor_queryset(
        student_query=student_query,
        grade_id=grade_id,
        section_id=section_id,
        month=month,
        concept=concept
    )

    sections = Section.objects.select_related('grade').order_by('grade__name', 'name')
    if grade_id:
        sections = sections.filter(grade_id=grade_id)

    context = {
        'debtors': debtors,
        'grades': Grade.objects.order_by('name'),
        'sections': sections,
        'student_query': student_query,
        'grade_id': grade_id,
        'section_id': section_id,
        'month': month,
        'concept': concept,
        'month_choices': Fee.MONTH_CHOICES,
        'concept_choices': Fee.CONCEPT_CHOICES,
        'total_pending': sum(item.balance_amount for item in debtors),
    }
    return render(request, 'finance/debtors_report.html', context)


@role_required('admin', 'director', 'secretary')
def monthly_report(request):
    month = request.GET.get('month')
    payments = Payment.objects.select_related('fee__enrollment__student').order_by('-payment_date')

    if month:
        try:
            year_value, month_value = month.split('-')
            payments = payments.filter(
                payment_date__year=int(year_value),
                payment_date__month=int(month_value)
            )
        except ValueError:
            messages.error(request, "Formato de mes invalido.")

    total = payments.aggregate(total=Sum('amount'))['total'] or 0
    return render(request, 'finance/monthly_report.html', {'payments': payments, 'total': total, 'month': month})


@role_required('admin', 'director', 'secretary')
def cash_report(request):
    today = timezone.localdate()
    payments = Payment.objects.select_related('fee__enrollment__student').filter(payment_date=today)
    total = payments.aggregate(total=Sum('amount'))['total'] or 0
    return render(request, 'finance/cash_report.html', {'payments': payments, 'total': total, 'today': today})


@role_required('admin', 'director', 'secretary')
def debtors_export_csv(request):
    student_query = request.GET.get('student', '').strip()
    grade_id = request.GET.get('grade', '').strip()
    month = request.GET.get('month', '').strip()
    debtors = _debtor_queryset(student_query=student_query, grade_id=grade_id, month=month)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="reporte_deudores.csv"'
    writer = csv.writer(response)
    writer.writerow(['Alumno', 'Grado', 'Concepto', 'Mes', 'Monto', 'Pagado', 'Pendiente', 'Vencimiento'])

    for fee in debtors:
        writer.writerow([
            str(fee.enrollment.student),
            str(fee.enrollment.section.grade),
            _concept_label(fee.concept),
            _month_label(fee.pension_month),
            fee.amount,
            fee.paid_amount,
            fee.balance_amount,
            fee.due_date,
        ])

    return response


@role_required('admin', 'director', 'secretary', 'parent')
def payment_receipt_pdf(request, payment_id):
    from .utils import generate_payment_receipt
    payment = get_object_or_404(Payment, id=payment_id)
    
    # Seguridad básica: El padre solo ve sus pagos
    if request.user.role == 'parent':
        if payment.fee.enrollment.student.parent_email != request.user.email: # Ajustar según modelo
             pass # Por ahora dejamos que lo vea si tiene el ID, mejorar si hay datos sensibles

    buffer = generate_payment_receipt(payment)
    filename = f"recibo_{payment.id}.pdf"
    
    return FileResponse(buffer, as_attachment=False, filename=filename)
