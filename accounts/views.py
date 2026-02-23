from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from academic.models import AcademicYear, Course, GradeRecord, Period, TeacherCourseAssignment
from schools.models import School
from enrollment.models import Enrollment
from students.models import Student
from .decorators import role_required
from .forms import SchoolIdentityForm, SchoolBusinessForm, UserCreateForm, UserUpdateForm
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
        if self.request.user.role == 'secretary':
            return reverse('secretary_dashboard')
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
    # Fetch teacher's assignments
    assignments = TeacherCourseAssignment.objects.filter(teacher=request.user).select_related(
        'course', 'section__grade', 'academic_year'
    )
    
    # Calculate relevant stats
    assigned_section_ids = assignments.values_list('section_id', flat=True).distinct()
    total_students = Enrollment.objects.filter(section_id__in=assigned_section_ids, status='active').count()
    total_courses = assignments.values_list('course_id', flat=True).distinct().count()
    
    # Filter grade records for this teacher
    assigned_course_ids = assignments.values_list('course_id', flat=True)
    total_grade_records = GradeRecord.objects.filter(course_id__in=assigned_course_ids).count()

    context = {
        'total_students': total_students,
        'total_courses': total_courses,
        'total_grade_records': total_grade_records,
        'assignments': assignments,
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
    from django.forms import modelformset_factory
    from .forms import CourseBookPriceForm, SchoolIdentityForm, SchoolBusinessForm
    
    active_year = AcademicYear.objects.filter(is_active=True).select_related('school').first()
    school_instance = School.objects.order_by('id').first()
    
    CourseFormSet = modelformset_factory(Course, form=CourseBookPriceForm, extra=0)

    # Inicializar formularios
    identity_form = SchoolIdentityForm(instance=school_instance)
    business_form = SchoolBusinessForm(instance=school_instance)
    course_formset = CourseFormSet(queryset=Course.objects.all().order_by('name'))

    if request.method == 'POST':
        if 'identity_config' in request.POST:
            identity_form = SchoolIdentityForm(request.POST, request.FILES, instance=school_instance)
            if identity_form.is_valid():
                identity_form.save()
                messages.success(request, "Identidad institucional actualizada.")
                return redirect('system_config')
        
        elif 'business_config' in request.POST:
            business_form = SchoolBusinessForm(request.POST, instance=school_instance)
            if business_form.is_valid():
                business_form.save()
                messages.success(request, "Costos del negocio actualizados.")
                return redirect('system_config')
        
        elif 'course_config' in request.POST:
            course_formset = CourseFormSet(request.POST)
            if course_formset.is_valid():
                course_formset.save()
                messages.success(request, "Precios de libros actualizados.")
                return redirect('system_config')

    periods = Period.objects.select_related('academic_year').order_by('-academic_year__year', 'start_date', 'name')

    context = {
        'active_year': active_year,
        'periods': periods,
        'school_form': identity_form, # Mantenemos nombre para compatibilidad o renombramos
        'identity_form': identity_form,
        'business_form': business_form,
        'course_formset': course_formset,
        'school_instance': school_instance,
    }
    return render(request, 'accounts/system_config.html', context)


@login_required
def user_profile(request):
    from .forms import SelfProfileForm
    if request.method == 'POST':
        form = SelfProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Tu perfil ha sido actualizado correctamente.")
            return redirect('user_profile')
    else:
        form = SelfProfileForm(instance=request.user)
    
    return render(request, 'accounts/user_profile.html', {
        'profile_user': request.user,
        'form': form
    })
    


@role_required('admin', 'director')
def activity_logs(request):
    logs = ActivityLog.objects.select_related('user')[:300]
    return render(request, 'accounts/activity_logs.html', {'logs': logs})
