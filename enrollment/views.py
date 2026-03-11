from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from students.models import Student

from .forms import EnrollmentForm
from .models import Enrollment


@role_required('admin', 'director', 'secretary')
def enrollment_dashboard(request):
    context = {
        'total_enrollments': Enrollment.objects.count(),
        'active_enrollments': Enrollment.objects.filter(status='active').count(),
        'retired_enrollments': Enrollment.objects.filter(status='retired').count(),
        'transferred_enrollments': Enrollment.objects.filter(status='transferred').count(),
    }
    return render(request, 'enrollment/enrollment_dashboard.html', context)


@role_required('admin', 'director', 'secretary')
def enrollment_list(request):
    enrollments = Enrollment.objects.select_related(
        'student',
        'section__grade',
        'academic_year'
    ).order_by('-enrolled_at')
    return render(request, 'enrollment/enrollment_list.html', {'enrollments': enrollments})


@role_required('admin', 'director', 'secretary')
def enrollment_create(request):
    messages.info(request, "La matricula nueva se registra desde Pagos > Registrar pago.")
    return redirect('payment_create')


@role_required('admin', 'director', 'secretary')
def enrollment_renew(request, enrollment_id):
    previous = get_object_or_404(Enrollment, id=enrollment_id)

    if request.method == 'POST':
        form = EnrollmentForm(request.POST)
        if form.is_valid():
            renewed = form.save(commit=False)
            renewed.student = previous.student
            renewed.status = 'active'
            renewed.save()
            messages.success(request, f"Matricula renovada para {renewed.student}.")
            return redirect('enrollment_list')
    else:
        form = EnrollmentForm(initial={
            'student': previous.student,
            'academic_year': previous.academic_year,
            'section': previous.section,
            'status': 'active',
        })
        form.fields['student'].disabled = True

    return render(request, 'enrollment/enrollment_renew_form.html', {'form': form, 'previous': previous})


@role_required('admin', 'director', 'secretary', 'teacher', 'parent')
def enrollment_history(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    history = Enrollment.objects.select_related(
        'section__grade',
        'academic_year'
    ).filter(student=student).order_by('-enrolled_at')
    return render(request, 'enrollment/enrollment_history.html', {'student': student, 'history': history})


@role_required('admin', 'director', 'secretary', 'teacher', 'parent')
def enrollment_detail(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related('student', 'section__grade', 'academic_year'),
        id=enrollment_id
    )
    return render(request, 'enrollment/enrollment_detail.html', {'enrollment': enrollment})


@role_required('admin', 'director', 'secretary')
def enrollment_edit(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related('student', 'section__grade', 'academic_year'),
        id=enrollment_id
    )

    if request.method == 'POST':
        form = EnrollmentForm(request.POST, instance=enrollment)
        if request.user.role == 'secretary' and not request.user.is_superuser:
            form.fields['student'].disabled = True

        if form.is_valid():
            updated = form.save(commit=False)
            # Secretaries can correct enrollment data but should not reassign a student to a different enrollment.
            if request.user.role == 'secretary' and not request.user.is_superuser:
                updated.student_id = enrollment.student_id
            updated.save()
            messages.success(request, "Matricula actualizada correctamente.")
            return redirect('enrollment_detail', enrollment_id=enrollment.id)
    else:
        form = EnrollmentForm(instance=enrollment)
        if request.user.role == 'secretary' and not request.user.is_superuser:
            form.fields['student'].disabled = True

    return render(request, 'enrollment/enrollment_edit_form.html', {
        'form': form,
        'enrollment': enrollment,
    })
