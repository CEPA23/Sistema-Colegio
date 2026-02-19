from django import forms
from django.core.exceptions import ValidationError

from academic.models import AcademicYear, Course, Grade, Level, Section, TeacherCourseAssignment
from schools.models import School

from .models import User


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': 'Ingresa una contraseña segura'}),
        help_text='La contraseña debe tener al menos 8 caracteres.'
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirma tu contraseña'}),
        help_text='Repite la contraseña para confirmar.'
    )

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'role',
            'teaching_grade',
            'teaching_section',
            'is_polyteacher',
            'teaching_courses',
            'teaching_grades',
            'phone',
            'is_active',
        ]
        labels = {
            'username': 'Nombre de usuario',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electrónico',
            'role': 'Rol',
            'teaching_grade': 'Grado que enseña',
            'teaching_section': 'Sección que enseña',
            'is_polyteacher': 'Es polidocente',
            'teaching_courses': 'Cursos que enseña (polidocente)',
            'teaching_grades': 'Grados que enseña (polidocente)',
            'phone': 'Teléfono',
            'is_active': 'Activo',
        }
        help_texts = {
            'username': 'El nombre de usuario debe ser único.',
            'email': 'Ingresa un correo electrónico válido.',
            'phone': 'Opcional. Formato: +1234567890',
            'is_polyteacher': 'Selecciona si el docente enseña múltiples cursos.',
        }
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'Ej: usuario123'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'Tu nombre'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Tu apellido'}),
            'email': forms.EmailInput(attrs={'placeholder': 'tuemail@ejemplo.com'}),
            'phone': forms.TextInput(attrs={'placeholder': '+1234567890'}),
            'teaching_courses': forms.SelectMultiple(attrs={'size': 5}),
            'teaching_grades': forms.SelectMultiple(attrs={'size': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teaching_grade'].queryset = Grade.objects.order_by('name')
        self.fields['teaching_section'].queryset = Section.objects.select_related('grade').order_by('grade__name', 'name')
        self.fields['teaching_courses'].queryset = Course.objects.order_by('name')
        self.fields['teaching_grades'].queryset = Grade.objects.order_by('name')
        self.fields['teaching_grade'].required = False
        self.fields['teaching_section'].required = False
        self.fields['is_polyteacher'].required = False
        self.fields['teaching_courses'].required = False
        self.fields['teaching_grades'].required = False
        self.fields['teaching_grade'].widget.attrs.update({'placeholder': 'Selecciona el grado'})
        self.fields['teaching_section'].widget.attrs.update({'placeholder': 'Selecciona la sección'})
        self.fields['teaching_courses'].widget.attrs.update({'placeholder': 'Selecciona los cursos'})
        self.fields['teaching_grades'].widget.attrs.update({'placeholder': 'Selecciona los grados'})

        # Dependencias para sección basada en grado
        grade = None
        if self.is_bound:
            grade = self.data.get('teaching_grade')
        elif self.instance.pk and self.instance.teaching_grade_id:
            grade = str(self.instance.teaching_grade_id)
        if grade:
            self.fields['teaching_section'].queryset = Section.objects.filter(grade_id=grade).order_by('name')

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Las contraseñas no coinciden.")
        if password1 and len(password1) < 8:
            raise forms.ValidationError("La contraseña debe tener al menos 8 caracteres.")
        return password2

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Este nombre de usuario ya está en uso.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Este correo electrónico ya está registrado.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        is_polyteacher = cleaned_data.get('is_polyteacher')
        teaching_grade = cleaned_data.get('teaching_grade')
        teaching_section = cleaned_data.get('teaching_section')
        teaching_courses = cleaned_data.get('teaching_courses')
        teaching_grades = cleaned_data.get('teaching_grades')

        if role == 'teacher':
            if is_polyteacher:
                if not teaching_courses:
                    self.add_error('teaching_courses', 'Debes seleccionar al menos un curso para un docente polidocente.')
                if not teaching_grades:
                    self.add_error('teaching_grades', 'Debes seleccionar al menos un grado para un docente polidocente.')
                # Limpiar campos no polidocentes
                cleaned_data['teaching_grade'] = None
                cleaned_data['teaching_section'] = None
            else:
                if not teaching_grade:
                    self.add_error('teaching_grade', 'Debes seleccionar el grado que enseña el docente.')
                if not teaching_section:
                    self.add_error('teaching_section', 'Debes seleccionar la sección que enseña el docente.')
                if teaching_section and teaching_grade and teaching_section.grade_id != teaching_grade.id:
                    self.add_error('teaching_section', 'La sección no pertenece al grado seleccionado.')
                # Limpiar campos polidocentes
                cleaned_data['teaching_courses'] = []
                cleaned_data['teaching_grades'] = []
        if role != 'teacher':
            cleaned_data['teaching_grade'] = None
            cleaned_data['teaching_section'] = None
            cleaned_data['is_polyteacher'] = False
            cleaned_data['teaching_courses'] = []
            cleaned_data['teaching_grades'] = []

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            user.set_password(password)
        if commit:
            user.save()
            # Asignar ManyToMany
            user.teaching_courses.set(self.cleaned_data.get('teaching_courses', []))
            user.teaching_grades.set(self.cleaned_data.get('teaching_grades', []))
            if user.role == 'teacher' and not user.is_polyteacher and user.teaching_section_id:
                active_year = AcademicYear.objects.filter(is_active=True).order_by('-year').first()
                if active_year:
                    # Asumir que enseña todos los cursos en su grado/sección
                    for course in Course.objects.order_by('name'):
                        TeacherCourseAssignment.objects.get_or_create(
                            teacher=user,
                            course=course,
                            section=user.teaching_section,
                            academic_year=active_year,
                            defaults={
                                'grade': user.teaching_grade,
                            },
                        )
            elif user.is_polyteacher:
                # Para polidocentes, asignar por cursos y grados
                active_year = AcademicYear.objects.filter(is_active=True).order_by('-year').first()
                if active_year:
                    for course in user.teaching_courses.all():
                        for grade in user.teaching_grades.all():
                            # Asumir sección por defecto o algo, pero como no hay sección, quizás crear sin sección
                            TeacherCourseAssignment.objects.get_or_create(
                                teacher=user,
                                course=course,
                                grade=grade,
                                academic_year=active_year,
                                defaults={},
                            )
        return user


class UserUpdateForm(UserCreateForm):
    password1 = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': 'Nueva contraseña (dejar en blanco para no cambiar)'}),
        help_text='Opcional. Si se deja en blanco, se mantendrá la contraseña actual.',
        required=False
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirmar nueva contraseña'}),
        help_text='Repite la nueva contraseña si deseas cambiarla.',
        required=False
    )

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1:
            if not password2:
                raise forms.ValidationError("Debes confirmar la nueva contraseña.")
            if password1 != password2:
                raise forms.ValidationError("Las contraseñas no coinciden.")
            if len(password1) < 8:
                raise forms.ValidationError("La contraseña debe tener al menos 8 caracteres.")
        return password2


class SchoolConfigForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ['name', 'logo', 'address', 'phone', 'email']
