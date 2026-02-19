from django.contrib import messages
from django.shortcuts import redirect
from django.shortcuts import get_object_or_404, render

from accounts.decorators import role_required
from enrollment.models import Enrollment
from finance.models import Fee

from .forms import StudentEnrollmentForm
from .models import Student


@role_required('admin', 'director', 'secretary', 'teacher')
def student_list(request):
    students = Student.objects.all().order_by('last_name', 'first_name')
    return render(request, 'students/student_list.html', {'students': students})


@role_required('admin', 'director', 'secretary', 'teacher')
def student_create(request):
    if request.method == 'POST':
        form = StudentEnrollmentForm(request.POST)
        if form.is_valid():
            student = form.save()
            enrollment = Enrollment.objects.create(
                student=student,
                academic_year=form.cleaned_data['academic_year'],
                section=form.cleaned_data['section'],
                status=form.cleaned_data['enrollment_status'],
            )
            messages.success(request, f"Alumno {student} registrado correctamente.")
            messages.success(
                request,
                f"Matricula creada en {enrollment.section.grade} {enrollment.section.name} ({enrollment.academic_year.year})."
            )
            return redirect('student_list')
    else:
        form = StudentEnrollmentForm()
    return render(request, 'students/student_form.html', {'form': form})


@role_required('admin', 'director', 'secretary', 'teacher', 'parent')
def student_profile(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    enrollments = Enrollment.objects.select_related(
        'section__grade',
        'academic_year'
    ).filter(student=student).order_by('-enrolled_at')
    fees = Fee.objects.select_related('enrollment').filter(enrollment__student=student)
    total_debt = sum(fee.balance for fee in fees)

    context = {
        'student': student,
        'enrollments': enrollments,
        'total_debt': total_debt,
    }
    return render(request, 'students/student_profile.html', context)
