from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from academic.models import AcademicYear, Course, GradeRecord, Period
from schools.models import School
from enrollment.models import Enrollment
from students.models import Student
from .decorators import role_required
from .forms import SchoolConfigForm, UserCreateForm, UserUpdateForm
from .models import ActivityLog, User


class RoleLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        next_url = self.get_redirect_url()
        if next_url:
            return next_url

        if self.request.user.role == 'teacher':
            return reverse('teacher_dashboard')
        if self.request.user.role == 'parent':
            return reverse('account_status')
        return reverse('dashboard')


@login_required
def dashboard(request):
    active_year = AcademicYear.objects.filter(is_active=True).select_related('school').first()
    recent_enrollments = Enrollment.objects.select_related(
        'student',
        'section__grade',
        'academic_year'
    ).order_by('-enrolled_at')[:6]

    context = {
        'active_year': active_year,
        'total_students': Student.objects.count(),
        'total_enrollments': Enrollment.objects.count(),
        'total_courses': Course.objects.count(),
        'total_grade_records': GradeRecord.objects.count(),
        'recent_enrollments': recent_enrollments,
    }
    return render(request, 'accounts/dashboard.html', context)


@role_required('teacher')
def teacher_dashboard(request):
    context = {
        'total_students': Student.objects.count(),
        'total_courses': Course.objects.count(),
        'total_grade_records': GradeRecord.objects.count(),
    }
    return render(request, 'accounts/teacher_dashboard.html', context)


@role_required('admin', 'director')
def user_management(request):
    show_user_form = request.GET.get('new') == '1'
    edit_user_id = request.GET.get('edit')
    edit_user = None

    if edit_user_id:
        edit_user = get_object_or_404(User, id=edit_user_id)
        if request.method == 'POST':
            form = UserUpdateForm(request.POST, instance=edit_user)
            if form.is_valid():
                form.save()
                messages.success(request, f"Usuario {edit_user.username} actualizado correctamente.")
                return redirect('user_management')
        else:
            form = UserUpdateForm(instance=edit_user)
        show_user_form = True
    elif request.method == 'POST':
        form = UserCreateForm(request.POST)
        show_user_form = True
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Usuario {user.username} creado correctamente.")
            return redirect('user_management')
    else:
        form = UserCreateForm(initial={'is_active': True})

    users = User.objects.select_related(
        'teaching_grade',
        'teaching_section__grade',
    ).order_by('username')
    return render(
        request,
        'accounts/user_management.html',
        {
            'users': users,
            'form': form,
            'show_user_form': show_user_form,
            'edit_user': edit_user,
        },
    )


@role_required('admin', 'director')
def user_delete(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        messages.error(request, "No puedes eliminar tu propio usuario.")
    elif user.is_superuser:
        messages.error(request, "No se pueden eliminar superusuarios desde este panel.")
    else:
        username = user.username
        user.delete()
        messages.success(request, f"Usuario {username} eliminado correctamente.")
    return redirect('user_management')


@role_required('admin', 'director')
def roles_permissions(request):
    role_matrix = [
        {'role': 'Administrador', 'access': 'Acceso total del sistema'},
        {'role': 'Director', 'access': 'Reportes globales y supervision academica'},
        {'role': 'Secretaria', 'access': 'Matricula, pagos y atencion administrativa'},
        {'role': 'Docente', 'access': 'Registro de notas, asistencias y reportes de su clase'},
        {'role': 'Padre', 'access': 'Consulta de boleta y estado de cuenta'},
    ]
    return render(request, 'accounts/roles_permissions.html', {'role_matrix': role_matrix})


@role_required('admin', 'director')
def system_config(request):
    active_year = AcademicYear.objects.filter(is_active=True).select_related('school').first()
    schools = School.objects.all().order_by('name')
    school_instance = School.objects.order_by('id').first()

    if request.method == 'POST':
        school_form = SchoolConfigForm(request.POST, request.FILES, instance=school_instance)
        if school_form.is_valid():
            school = school_form.save()
            messages.success(request, f"Configuracion actualizada para {school.name}.")
            return redirect('system_config')
    else:
        school_form = SchoolConfigForm(instance=school_instance)

    periods = Period.objects.select_related('academic_year').order_by('-academic_year__year', 'start_date', 'name')

    context = {
        'active_year': active_year,
        'schools': schools,
        'periods': periods,
        'school_form': school_form,
        'school_instance': school_instance,
    }
    return render(request, 'accounts/system_config.html', context)


@login_required
def user_profile(request):
    return render(request, 'accounts/user_profile.html', {'profile_user': request.user})


@role_required('admin', 'director')
def activity_logs(request):
    logs = ActivityLog.objects.select_related('user')[:300]
    return render(request, 'accounts/activity_logs.html', {'logs': logs})
