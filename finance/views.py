import csv
from decimal import Decimal
from datetime import date

from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q, Sum
from django.http import HttpResponse, JsonResponse, FileResponse, Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone

from accounts.decorators import role_required
from academic.models import AcademicYear, Course, Grade, Section
from core.student_ordering import (
    order_queryset_by_student_name,
    resolve_student_order,
    student_order_context,
)
from enrollment.models import Enrollment
from schools.models import School
from students.models import Student

from .forms import PaymentRegistrationForm, QuickEnrollmentForm
from .models import Fee, Payment


def _concept_label(concept_code):
    return dict(Fee.CONCEPT_CHOICES).get(concept_code, concept_code)


def _month_label(month_value):
    try:
        month_int = int(month_value)
    except (TypeError, ValueError):
        return '-'
    return dict(Fee.MONTH_CHOICES).get(month_int, '-')


def _month_labels(month_values):
    return [_month_label(month) for month in month_values]


def _apply_student_name_filter(queryset, student_query):
    if not student_query:
        return queryset
    name_parts = [part for part in student_query.split() if part]
    for part in name_parts:
        queryset = queryset.filter(
            Q(enrollment__student__first_name__icontains=part)
            | Q(enrollment__student__last_name__icontains=part)
        )
    return queryset


def _fee_detail_label(fee):
    if fee.concept == Fee.CONCEPT_PENSION:
        return _month_label(fee.pension_month)
    if fee.concept == Fee.CONCEPT_BOOK and fee.course_id:
        return fee.course.name
    return '-'


DEBT_STATE_CHOICES = (
    ('', 'Todas'),
    ('sin_abono', 'Sin abono'),
    ('fraccionado', 'Fraccionado'),
)


def _safe_month(month_value, default=None):
    try:
        month_int = int(month_value)
    except (TypeError, ValueError):
        return default
    return month_int if 1 <= month_int <= 12 else default


def _normalize_month_list(month_values):
    normalized = []
    for month_value in month_values or []:
        month_int = _safe_month(month_value)
        if month_int and month_int not in normalized:
            normalized.append(month_int)
    return sorted(normalized)


def _active_academic_year():
    return AcademicYear.objects.filter(is_active=True).order_by('-year').first()


def _school_prices():
    school = School.objects.first()
    if not school:
        return {
            'pension': Decimal('0.00'),
            'matricula': Decimal('0.00'),
            'material': Decimal('0.00'),
        }
    return {
        'pension': school.pension_price,
        'matricula': school.enrollment_price,
        'material': school.supplies_price,
    }


def _ensure_debt(
    enrollment,
    concept,
    amount_total,
    due_date,
    pension_month=None,
    course=None,
    inventory_product=None,
):
    if amount_total is None or amount_total <= Decimal('0.00'):
        return None

    filters = {
        'enrollment': enrollment,
        'concept': concept,
    }
    if concept == Fee.CONCEPT_PENSION:
        filters['pension_month'] = pension_month
        filters['course__isnull'] = True
    elif concept == Fee.CONCEPT_BOOK:
        filters['inventory_product'] = inventory_product
        filters['pension_month__isnull'] = True
        filters['course__isnull'] = True
    elif concept in [Fee.CONCEPT_BAND_UNIFORM, Fee.CONCEPT_SCHOOL_UNIFORM, Fee.CONCEPT_PRODUCT]:
        filters['inventory_product'] = inventory_product
        filters['pension_month__isnull'] = True
        filters['course__isnull'] = True
    else:
        filters['pension_month__isnull'] = True
        filters['course__isnull'] = True
        filters['inventory_product__isnull'] = True

    debt = Fee.objects.filter(**filters).order_by('id').first()
    if not debt:
        debt = Fee.objects.create(
            enrollment=enrollment,
            concept=concept,
            pension_month=pension_month if concept == Fee.CONCEPT_PENSION else None,
            inventory_product=inventory_product,
            amount=amount_total,
            due_date=due_date,
            amount_paid=Decimal('0.00'),
            status='pending',
        )
        return debt

    update_fields = []
    if debt.amount_paid == Decimal('0.00') and debt.amount != amount_total:
        debt.amount = amount_total
        update_fields.append('amount')
    if debt.amount_paid == Decimal('0.00') and debt.due_date != due_date:
        debt.due_date = due_date
        update_fields.append('due_date')
    if update_fields:
        debt.save(update_fields=update_fields)
    debt.refresh_status()
    return debt


def _ensure_debts_for_enrollment(enrollment, target_month=None, selected_product=None, concept=None):
    prices = _school_prices()
    debt_month = _safe_month(target_month, timezone.localdate().month)
    debt_year = enrollment.academic_year.year
    due_date_pension = date(debt_year, debt_month, 1)
    enrollment_due = enrollment.enrolled_at.date()

    # Standard debts if not explicitly registering a specific product payment
    if not concept:
        _ensure_debt(
            enrollment=enrollment,
            concept=Fee.CONCEPT_PENSION,
            amount_total=prices['pension'],
            due_date=due_date_pension,
            pension_month=debt_month,
        )
        _ensure_debt(
            enrollment=enrollment,
            concept=Fee.CONCEPT_ENROLLMENT,
            amount_total=prices['matricula'],
            due_date=enrollment_due,
        )
        _ensure_debt(
            enrollment=enrollment,
            concept=Fee.CONCEPT_SCHOOL_SUPPLIES,
            amount_total=prices['material'],
            due_date=enrollment_due,
        )
    
    # Specific debt for Books or Uniforms
    if concept in [Fee.CONCEPT_BOOK, Fee.CONCEPT_BAND_UNIFORM, Fee.CONCEPT_SCHOOL_UNIFORM, Fee.CONCEPT_PRODUCT] and selected_product:
        _ensure_debt(
            enrollment=enrollment,
            concept=concept,
            amount_total=selected_product.price,
            due_date=timezone.localdate(),
            inventory_product=selected_product,
        )


def _ensure_pension_debts_for_months(enrollment, pension_months, pension_price):
    prices = _school_prices()
    debt_year = enrollment.academic_year.year
    debts = []
    for month_value in _normalize_month_list(pension_months):
        debt = _ensure_debt(
            enrollment=enrollment,
            concept=Fee.CONCEPT_PENSION,
            amount_total=pension_price if pension_price is not None else prices['pension'],
            due_date=date(debt_year, month_value, 1),
            pension_month=month_value,
        )
        if debt:
            debts.append(debt)
    return debts


def _ensure_active_enrollment_debts(target_month=None):
    active_year = _active_academic_year()
    if not active_year:
        return
    debt_month = _safe_month(target_month, timezone.localdate().month)
    enrollments = Enrollment.objects.filter(
        academic_year=active_year,
        status='active',
    ).select_related('academic_year')
    for enrollment in enrollments:
        _ensure_debts_for_enrollment(enrollment, target_month=debt_month)


def _debtor_queryset(
    student_query='',
    student_id='',
    grade_id='',
    section_id='',
    month='',
    concept='',
    debt_state='',
    student_order='az',
):
    fees = Fee.objects.select_related(
        'enrollment__student',
        'enrollment__section__grade',
        'enrollment__academic_year',
        'course',
    )
    fees = fees.annotate(
        paid_amount=F('amount_paid'),
        balance_amount=F('amount') - F('amount_paid'),
    ).filter(balance_amount__gt=0)

    if student_id:
        fees = fees.filter(enrollment__student_id=student_id)
    else:
        fees = _apply_student_name_filter(fees, student_query)

    if grade_id:
        fees = fees.filter(enrollment__section__grade_id=grade_id)

    if section_id:
        fees = fees.filter(enrollment__section_id=section_id)

    if concept:
        fees = fees.filter(concept=concept)

    if month:
        month_int = _safe_month(month)
        if month_int:
            fees = fees.filter(concept=Fee.CONCEPT_PENSION, pension_month=month_int)

    if debt_state == 'sin_abono':
        fees = fees.filter(paid_amount=0)
    elif debt_state == 'fraccionado':
        fees = fees.filter(paid_amount__gt=0)

    return order_queryset_by_student_name(
        fees,
        prefix='enrollment__student',
        student_order=student_order,
        extra_fields=['due_date', 'id'],
    )


@role_required('admin', 'director')
def finance_dashboard(request):
    today = timezone.localdate()
    _ensure_active_enrollment_debts(target_month=today.month)
    fees = Fee.objects.select_related('enrollment__student')
    total_billed = fees.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_paid = fees.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
    total_pending = total_billed - total_paid

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


@role_required('admin', 'director', 'parent')
def account_status(request):
    student_order = resolve_student_order(request)
    _ensure_active_enrollment_debts(target_month=timezone.localdate().month)
    fees = order_queryset_by_student_name(
        Fee.objects.select_related(
        'enrollment__student',
        'enrollment__academic_year'
        ),
        prefix='enrollment__student',
        student_order=student_order,
        extra_fields=['due_date', 'id'],
    )

    total_pending = sum(f.balance for f in fees)
    context = {
        'fees': fees,
        'total_pending': total_pending,
    }
    context.update(student_order_context(request, student_order))
    return render(request, 'finance/account_status.html', context)


@role_required('admin', 'director', 'secretary')
def payment_create(request):
    today = timezone.localdate()
    _ensure_active_enrollment_debts(target_month=today.month)

    if request.method == 'POST':
        form = PaymentRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            enrollment = form.cleaned_data['enrollment']
            concept = form.cleaned_data['concept']
            pension_price = form.cleaned_data.get('pension_price')
            pension_months = _normalize_month_list(form.cleaned_data.get('pension_months'))
            inventory_product = form.cleaned_data.get('inventory_product')
            amount = form.cleaned_data['amount']
            method = form.cleaned_data['method']
            proof_image = form.cleaned_data['proof_image']
            comment = form.cleaned_data['comment']

            if concept == Fee.CONCEPT_PENSION:
                if not pension_months:
                    form.add_error('pension_months', 'Debes seleccionar al menos un mes para una pension.')
                if pension_price is None:
                    form.add_error('pension_price', 'Debes indicar el costo de la pension.')
                if not form.errors:
                    _ensure_pension_debts_for_months(enrollment, pension_months, pension_price)
                    fee_map = {
                        fee.pension_month: fee
                        for fee in Fee.objects.filter(
                            enrollment=enrollment,
                            concept=Fee.CONCEPT_PENSION,
                            pension_month__in=pension_months,
                        )
                    }
                    selected_fees = []
                    missing_months = []
                    already_paid_months = []
                    partial_months = []
                    for month_value in pension_months:
                        fee = fee_map.get(month_value)
                        if not fee:
                            missing_months.append(_month_label(month_value))
                            continue
                        if fee.balance <= Decimal('0.00'):
                            already_paid_months.append(_month_label(month_value))
                            continue
                        if fee.balance != fee.amount:
                            partial_months.append(_month_label(month_value))
                            continue
                        selected_fees.append(fee)

                    if missing_months:
                        form.add_error(None, f"No se pudieron encontrar las deudas de: {', '.join(missing_months)}.")
                    if already_paid_months:
                        form.add_error(None, f"Los meses {', '.join(already_paid_months)} ya se encuentran pagados.")
                    if partial_months:
                        form.add_error(None, f"Los meses {', '.join(partial_months)} tienen pagos parciales y deben cobrarse individualmente.")

                    expected_total = (pension_price or Decimal('0.00')) * Decimal(len(selected_fees))
                    if selected_fees and amount != expected_total:
                        form.add_error('amount', f"El total para {len(selected_fees)} mes(es) es S/ {expected_total:.2f}.")

                    if not form.errors:
                        month_names = _month_labels(pension_months)
                        batch_comment = f"Pago multiple de pension: {', '.join(month_names)}"
                        if comment:
                            batch_comment = f"{batch_comment}. {comment}"

                        payment_ids = []
                        with transaction.atomic():
                            for fee in selected_fees:
                                payment = Payment.objects.create(
                                    fee=fee,
                                    amount=pension_price,
                                    method=method,
                                    proof_image=proof_image,
                                    comment=batch_comment,
                                )
                                payment_ids.append(payment.id)

                        from django.utils.safestring import mark_safe
                        from django.urls import reverse
                        receipt_url = reverse('payment_receipt_pdf', args=[payment_ids[0]])
                        if len(payment_ids) > 1:
                            receipt_url = f"{receipt_url}?payment_ids={','.join(str(pid) for pid in payment_ids)}"
                        receipt_label = "Imprimir boleta"
                        if len(payment_ids) > 1:
                            receipt_label = "Imprimir boleta unica"

                        if len(payment_ids) == 1:
                            messages.success(
                                request,
                                mark_safe(
                                    f"Pago registrado para {enrollment.student}. "
                                    f"<a href='{receipt_url}' target='_blank' class='btn btn-subtle' style='margin-left:10px;'>{receipt_label}</a>"
                                )
                            )
                        else:
                            total_paid = expected_total
                            messages.success(
                                request,
                                mark_safe(
                                    f"Pago registrado para {enrollment.student}. "
                                    f"Se cobraron {len(selected_fees)} meses ({', '.join(month_names)}) por S/ {total_paid:.2f}. "
                                    f"<a href='{receipt_url}' target='_blank' class='btn btn-subtle' style='margin-left:10px;'>{receipt_label}</a>"
                                )
                            )
                        return redirect('payment_history')
            else:
                _ensure_debts_for_enrollment(
                    enrollment=enrollment,
                    target_month=today.month,
                    selected_product=inventory_product,
                    concept=concept,
                )

                fee_qs = Fee.objects.filter(enrollment=enrollment, concept=concept)
                if concept == Fee.CONCEPT_BOOK:
                    fee_qs = fee_qs.filter(inventory_product=inventory_product)
                elif concept in [Fee.CONCEPT_BAND_UNIFORM, Fee.CONCEPT_SCHOOL_UNIFORM, Fee.CONCEPT_PRODUCT]:
                    fee_qs = fee_qs.filter(inventory_product=inventory_product)
                else:
                    fee_qs = fee_qs.filter(pension_month__isnull=True, course__isnull=True, inventory_product__isnull=True)

                fee = None
                candidates = list(fee_qs.order_by('due_date', 'id'))
                for candidate in candidates:
                    if candidate.balance > Decimal('0.00'):
                        fee = candidate
                        break
                if fee is None and candidates:
                    fee = candidates[0]
                if not fee:
                    form.add_error(
                        None,
                        "No existe una deuda registrada para ese alumno y concepto. "
                        "Primero debe existir la deuda y luego registrar el pago.",
                    )
                elif fee.balance <= Decimal('0.00'):
                    form.add_error(None, "Esa deuda ya se encuentra pagada.")

                if fee and amount > fee.balance:
                    form.add_error('amount', f"El saldo de esta deuda es S/ {fee.balance}.")
                elif fee:
                    payment = Payment.objects.create(
                        fee=fee,
                        amount=amount,
                        method=method,
                        proof_image=proof_image,
                        comment=comment,
                    )
                    is_inv_concept = concept in [Fee.CONCEPT_PRODUCT, Fee.CONCEPT_BOOK, Fee.CONCEPT_BAND_UNIFORM, Fee.CONCEPT_SCHOOL_UNIFORM]
                    if is_inv_concept and fee.inventory_product:
                        from inventory.views import _discount_stock
                        try:
                            _discount_stock(
                                product=fee.inventory_product,
                                quantity=fee.inventory_quantity,
                                reference=f'Pago #{payment.id} - {fee.enrollment.student}',
                                payment=payment,
                                user=request.user,
                            )
                        except ValueError as stock_err:
                            messages.warning(request, f'Pago registrado, pero no se pudo descontar stock: {stock_err}')
                    from django.utils.safestring import mark_safe
                    from django.urls import reverse
                    receipt_url = reverse('payment_receipt_pdf', args=[payment.id])
                    messages.success(
                        request,
                        mark_safe(
                            f"Pago registrado para {payment.fee.enrollment.student}. "
                            f"<a href='{receipt_url}' target='_blank' class='btn btn-subtle' style='margin-left:10px;'>Imprimir Boleta</a>"
                        )
                    )
                    return redirect('payment_history')
    else:
        form = PaymentRegistrationForm()
    school = School.objects.first()
    grades = Grade.objects.order_by('name')
    sections = Section.objects.select_related('grade').order_by('grade__name', 'name')

    # Prices for config-based concepts (matricula, pension, material escolar)
    suggested_prices = {
        'pension': str(school.pension_price) if school else '200.00',
        'matricula': str(school.enrollment_price) if school else '300.00',
        'material_escolar': str(school.supplies_price) if school else '50.00',
    }

    # Load inventory products for libro, uniforme_banda, uniforme_colegio
    from inventory.models import Product
    inv_products = Product.objects.filter(is_active=True).values('id', 'name', 'category', 'price', 'stock')

    inventory_by_category = {}
    for p in inv_products:
        cat = p['category']
        if cat not in inventory_by_category:
            inventory_by_category[cat] = []
        inventory_by_category[cat].append({
            'id': p['id'],
            'name': p['name'],
            'price': str(p['price']),
            'stock': p['stock'],
        })

    return render(request, 'finance/payment_form.html', {
        'form': form,
        'suggested_prices': suggested_prices,
        'inventory_by_category': inventory_by_category,
        'grades': grades,
        'sections': sections,
    })


@role_required('admin', 'director', 'secretary')
def quick_enrollment_create(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Metodo no permitido.'}, status=405)

    form = QuickEnrollmentForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'ok': False, 'errors': form.errors}, status=400)

    active_year = AcademicYear.objects.filter(is_active=True).order_by('-year').first()
    if not active_year:
        return JsonResponse({'ok': False, 'error': 'No hay un anio academico activo.'}, status=400)

    section = form.cleaned_data['section']
    student_data = {
        'first_name': form.cleaned_data['first_name'].strip(),
        'last_name': form.cleaned_data['last_name'].strip(),
        'birth_date': form.cleaned_data['birth_date'],
        'address': form.cleaned_data['address'].strip(),
        'parent_name': form.cleaned_data['parent_name'].strip(),
        'parent_phone': form.cleaned_data['parent_phone'].strip(),
        'father_name': form.cleaned_data['father_name'].strip(),
        'father_phone': form.cleaned_data['father_phone'].strip(),
        'mother_name': form.cleaned_data['mother_name'].strip(),
        'mother_phone': form.cleaned_data['mother_phone'].strip(),
    }

    student, created = Student.objects.get_or_create(
        dni=form.cleaned_data['dni'],
        defaults=student_data,
    )
    if not created:
        for field_name, field_value in student_data.items():
            setattr(student, field_name, field_value)
        student.save()

    enrollment = Enrollment.objects.filter(student=student, academic_year=active_year).order_by('-id').first()
    if enrollment:
        enrollment.section = section
        enrollment.status = 'active'
        enrollment.save(update_fields=['section', 'status'])
    else:
        enrollment = Enrollment.objects.create(
            student=student,
            academic_year=active_year,
            section=section,
            status='active',
        )

    _ensure_debts_for_enrollment(enrollment, target_month=timezone.localdate().month)

    return JsonResponse({
        'ok': True,
        'enrollment_id': enrollment.id,
        'student_name': str(student),
        'label': f"{student} - {section.grade} {section.name} ({active_year.year})",
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


@role_required('admin', 'director', 'secretary')
def debtors_student_search(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})

    pending_debts = Fee.objects.annotate(
        balance_amount=F('amount') - F('amount_paid')
    ).filter(balance_amount__gt=0)
    pending_debts = _apply_student_name_filter(pending_debts, query)

    rows = pending_debts.values(
        'enrollment__student_id',
        'enrollment__student__first_name',
        'enrollment__student__last_name',
    ).distinct()[:20]

    results = []
    for row in rows:
        full_name = f"{row['enrollment__student__first_name']} {row['enrollment__student__last_name']}".strip()
        results.append({
            'student_id': row['enrollment__student_id'],
            'student_name': full_name,
        })
    return JsonResponse({'results': results})


@role_required('admin', 'director', 'secretary', 'parent')
def payment_history(request):
    student_order = resolve_student_order(request)
    query = request.GET.get('q', '').strip()
    payments = Payment.objects.select_related(
        'fee__enrollment__student',
        'fee__enrollment__section__grade',
    )
    payments = _apply_payment_search_filter(payments, query)
    payments = order_queryset_by_student_name(
        payments,
        prefix='fee__enrollment__student',
        student_order=student_order,
        extra_fields=['-payment_date', '-id'],
    )
    context = {
        'payments': payments,
        'payment_query': query,
    }
    context.update(student_order_context(request, student_order))
    return render(request, 'finance/payment_history.html', context)


@role_required('admin', 'director', 'secretary')
def debtors_report(request):
    from academic.models import Section
    student_order = resolve_student_order(request)
    student_query = request.GET.get('student', '').strip()
    student_id = request.GET.get('student_id', '').strip()
    grade_id = request.GET.get('grade', '').strip()
    section_id = request.GET.get('section', '').strip()
    month = request.GET.get('month', '').strip()
    concept = request.GET.get('concept', '').strip()
    debt_state = request.GET.get('debt_state', '').strip()
    month_int = _safe_month(month)
    _ensure_active_enrollment_debts(target_month=month_int or timezone.localdate().month)

    if student_id and not student_query:
        selected_student = Student.objects.filter(id=student_id).only('first_name', 'last_name').first()
        if selected_student:
            student_query = f"{selected_student.first_name} {selected_student.last_name}".strip()

    debtors = _debtor_queryset(
        student_query=student_query,
        student_id=student_id,
        grade_id=grade_id,
        section_id=section_id,
        month=month,
        concept=concept,
        debt_state=debt_state,
        student_order=student_order,
    )

    sections = Section.objects.select_related('grade').order_by('grade__name', 'name')
    if grade_id:
        sections = sections.filter(grade_id=grade_id)

    context = {
        'debtors': debtors,
        'grades': Grade.objects.order_by('name'),
        'sections': sections,
        'student_query': student_query,
        'student_id': student_id,
        'grade_id': grade_id,
        'section_id': section_id,
        'month': month,
        'concept': concept,
        'debt_state': debt_state,
        'month_choices': Fee.MONTH_CHOICES,
        'concept_choices': Fee.CONCEPT_CHOICES,
        'debt_state_choices': DEBT_STATE_CHOICES,
        'total_pending': sum(item.balance_amount for item in debtors),
        **student_order_context(request, student_order),
    }
    return render(request, 'finance/debtors_report.html', context)


@role_required('admin', 'director')
def monthly_report(request):
    student_order = resolve_student_order(request)
    month = request.GET.get('month')
    payments = Payment.objects.select_related('fee__enrollment__student')

    if month:
        try:
            year_value, month_value = month.split('-')
            payments = payments.filter(
                payment_date__year=int(year_value),
                payment_date__month=int(month_value)
            )
        except ValueError:
            messages.error(request, "Formato de mes invalido.")

    payments = order_queryset_by_student_name(
        payments,
        prefix='fee__enrollment__student',
        student_order=student_order,
        extra_fields=['-payment_date', '-id'],
    )
    total = payments.aggregate(total=Sum('amount'))['total'] or 0
    context = {'payments': payments, 'total': total, 'month': month}
    context.update(student_order_context(request, student_order))
    return render(request, 'finance/monthly_report.html', context)


@role_required('admin', 'director')
def cash_report(request):
    student_order = resolve_student_order(request)
    today = timezone.localdate()
    payments = order_queryset_by_student_name(
        Payment.objects.select_related('fee__enrollment__student').filter(payment_date=today),
        prefix='fee__enrollment__student',
        student_order=student_order,
        extra_fields=['-id'],
    )
    total = payments.aggregate(total=Sum('amount'))['total'] or 0
    context = {'payments': payments, 'total': total, 'today': today}
    context.update(student_order_context(request, student_order))
    return render(request, 'finance/cash_report.html', context)


@role_required('admin', 'director', 'secretary')
def debtors_export_csv(request):
    student_order = resolve_student_order(request)
    student_query = request.GET.get('student', '').strip()
    student_id = request.GET.get('student_id', '').strip()
    grade_id = request.GET.get('grade', '').strip()
    section_id = request.GET.get('section', '').strip()
    concept = request.GET.get('concept', '').strip()
    month = request.GET.get('month', '').strip()
    debt_state = request.GET.get('debt_state', '').strip()
    month_int = _safe_month(month)
    _ensure_active_enrollment_debts(target_month=month_int or timezone.localdate().month)
    debtors = _debtor_queryset(
        student_query=student_query,
        student_id=student_id,
        grade_id=grade_id,
        section_id=section_id,
        concept=concept,
        month=month,
        debt_state=debt_state,
        student_order=student_order,
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="reporte_deudores.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'Alumno',
        'Grado',
        'Seccion',
        'Concepto',
        'Detalle',
        'Monto',
        'Pagado',
        'Pendiente',
        'Estado deuda',
        'Vencimiento',
    ])

    for fee in debtors:
        debt_status = 'Fraccionado' if fee.paid_amount > 0 else 'Sin abono'
        writer.writerow([
            str(fee.enrollment.student),
            str(fee.enrollment.section.grade),
            str(fee.enrollment.section.name),
            _concept_label(fee.concept),
            _fee_detail_label(fee),
            fee.amount,
            fee.paid_amount,
            fee.balance_amount,
            debt_status,
            fee.due_date,
        ])

    return response


def _load_receipt_payments(request, payment_id):
    payment_ids_raw = request.GET.get('payment_ids', '').strip()
    if not payment_ids_raw:
        payment = get_object_or_404(Payment, id=payment_id)
        return payment, [payment]

    payment_ids = []
    for chunk in payment_ids_raw.split(','):
        chunk = chunk.strip()
        if chunk.isdigit():
            payment_ids.append(int(chunk))
    if payment_id not in payment_ids:
        payment_ids.insert(0, payment_id)

    payments = list(
        Payment.objects.select_related(
            'fee__enrollment__student',
            'fee__enrollment__academic_year__school',
            'fee__course',
        ).filter(id__in=payment_ids).order_by('payment_date', 'id')
    )
    if not payments:
        raise Http404("No se encontraron pagos para la boleta solicitada.")
    return payments[0], payments


def _apply_payment_search_filter(queryset, query):
    if not query:
        return queryset

    normalized = query.strip()
    q_lower = normalized.lower()
    filters = (
        Q(fee__enrollment__student__first_name__icontains=normalized)
        | Q(fee__enrollment__student__last_name__icontains=normalized)
        | Q(fee__enrollment__student__dni__icontains=normalized)
        | Q(comment__icontains=normalized)
    )

    concept_map = {
        'matricula': Fee.CONCEPT_ENROLLMENT,
        'pension': Fee.CONCEPT_PENSION,
        'mensualidad': Fee.CONCEPT_PENSION,
        'material': Fee.CONCEPT_SCHOOL_SUPPLIES,
        'libro': Fee.CONCEPT_BOOK,
        'uniforme': Fee.CONCEPT_SCHOOL_UNIFORM,
        'banda': Fee.CONCEPT_BAND_UNIFORM,
        'inventario': Fee.CONCEPT_PRODUCT,
        'cash': Payment.METHOD_CASH,
        'efectivo': Payment.METHOD_CASH,
        'transferencia': Payment.METHOD_TRANSFER,
        'yape': Payment.METHOD_YAPE_PLIN,
        'plin': Payment.METHOD_YAPE_PLIN,
    }

    concept = concept_map.get(q_lower)
    if concept:
        filters |= Q(fee__concept=concept)

    if normalized.isdigit():
        filters |= Q(amount=normalized)

    return queryset.filter(filters)


@role_required('admin', 'director', 'secretary', 'parent')
def payment_receipt_pdf(request, payment_id):
    from .utils import generate_payment_receipt
    payment, payments = _load_receipt_payments(request, payment_id)

    # Seguridad básica: El padre solo ve sus pagos
    if request.user.role == 'parent':
        if payment.fee.enrollment.student.parent_email != request.user.email:  # Ajustar según modelo
            pass  # Por ahora dejamos que lo vea si tiene el ID, mejorar si hay datos sensibles

    buffer = generate_payment_receipt(payments)
    filename = f"recibo_{payment.id}_lote.pdf" if len(payments) > 1 else f"recibo_{payment.id}.pdf"

    return FileResponse(buffer, as_attachment=False, filename=filename)

