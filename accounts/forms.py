from django import forms

from academic.models import AcademicYear, Course, Grade, Section, TeacherCourseAssignment
from schools.models import School

from .models import User


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Contrasena',
        widget=forms.PasswordInput(attrs={'placeholder': 'Ingresa una contrasena segura'}),
        help_text='La contrasena debe tener al menos 8 caracteres.',
    )
    password2 = forms.CharField(
        label='Confirmar contrasena',
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirma tu contrasena'}),
        help_text='Repite la contrasena para confirmar.',
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
            'teaching_sections',
            'phone',
            'is_active',
        ]
        labels = {
            'username': 'Nombre de usuario',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electronico',
            'role': 'Rol',
            'teaching_grade': 'Grado que ensena',
            'teaching_section': 'Seccion que ensena',
            'is_polyteacher': 'Tambien dicta polidocencia',
            'teaching_courses': 'Cursos que ensena (polidocencia)',
            'teaching_grades': 'Grados que ensena (auto)',
            'teaching_sections': 'Secciones que ensena (polidocencia)',
            'phone': 'Telefono',
            'is_active': 'Activo',
        }
        help_texts = {
            'username': 'El nombre de usuario debe ser unico.',
            'email': 'Ingresa un correo electronico valido.',
            'phone': 'Opcional. Formato: +1234567890',
            'is_polyteacher': 'Marca esta opcion si la docente tambien dicta cursos de polidocencia.',
        }
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'Ej: usuario123'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'Tu nombre'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Tu apellido'}),
            'email': forms.EmailInput(attrs={'placeholder': 'tuemail@ejemplo.com'}),
            'phone': forms.TextInput(attrs={'placeholder': '+1234567890'}),
            'teaching_courses': forms.SelectMultiple(attrs={'size': 5}),
            'teaching_grades': forms.SelectMultiple(attrs={'size': 5}),
            'teaching_sections': forms.SelectMultiple(attrs={'size': 8}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teaching_grade'].queryset = Grade.objects.order_by('name')
        self.fields['teaching_section'].queryset = Section.objects.select_related('grade').order_by('grade__name', 'name')
        self.fields['teaching_courses'].queryset = Course.objects.order_by('name')
        self.fields['teaching_grades'].queryset = Grade.objects.order_by('name')
        self.fields['teaching_sections'].queryset = Section.objects.select_related('grade').order_by('grade__name', 'name')
        self.fields['teaching_grade'].required = False
        self.fields['teaching_section'].required = False
        self.fields['is_polyteacher'].required = False
        self.fields['teaching_courses'].required = False
        self.fields['teaching_grades'].required = False
        self.fields['teaching_sections'].required = False
        self.fields['teaching_grade'].widget.attrs.update({'placeholder': 'Selecciona el grado'})
        self.fields['teaching_section'].widget.attrs.update({'placeholder': 'Selecciona la seccion'})
        self.fields['teaching_courses'].widget.attrs.update({'placeholder': 'Selecciona los cursos'})
        self.fields['teaching_grades'].widget.attrs.update({'placeholder': 'Selecciona los grados'})
        self.fields['teaching_sections'].widget.attrs.update({'placeholder': 'Selecciona las secciones'})
        self.fields['teaching_grades'].widget = forms.MultipleHiddenInput()

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
            raise forms.ValidationError('Las contrasenas no coinciden.')
        if password1 and len(password1) < 8:
            raise forms.ValidationError('La contrasena debe tener al menos 8 caracteres.')
        return password2

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Este nombre de usuario ya esta en uso.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Este correo electronico ya esta registrado.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        is_polyteacher = cleaned_data.get('is_polyteacher')
        teaching_grade = cleaned_data.get('teaching_grade')
        teaching_section = cleaned_data.get('teaching_section')
        teaching_courses = cleaned_data.get('teaching_courses')
        teaching_sections = cleaned_data.get('teaching_sections')

        if role == 'teacher':
            if teaching_grade and not teaching_section:
                self.add_error('teaching_section', 'Debes seleccionar la seccion de la tutoria.')
            if teaching_section and not teaching_grade:
                self.add_error('teaching_grade', 'Debes seleccionar el grado de la tutoria.')
            if teaching_section and teaching_grade and teaching_section.grade_id != teaching_grade.id:
                self.add_error('teaching_section', 'La seccion no pertenece al grado seleccionado.')

            if is_polyteacher:
                if not teaching_courses:
                    self.add_error('teaching_courses', 'Debes seleccionar al menos un curso para un docente polidocente.')
                if not teaching_sections:
                    self.add_error('teaching_sections', 'Debes seleccionar al menos una seccion para un docente polidocente.')
                cleaned_data['teaching_grades'] = (
                    Grade.objects.filter(section__in=teaching_sections).distinct()
                    if teaching_sections else Grade.objects.none()
                )
            else:
                if not teaching_grade:
                    self.add_error('teaching_grade', 'Debes seleccionar el grado que ensena el docente.')
                if not teaching_section:
                    self.add_error('teaching_section', 'Debes seleccionar la seccion que ensena el docente.')
                cleaned_data['teaching_courses'] = Course.objects.none()
                cleaned_data['teaching_grades'] = Grade.objects.none()
                cleaned_data['teaching_sections'] = Section.objects.none()
        else:
            cleaned_data['teaching_grade'] = None
            cleaned_data['teaching_section'] = None
            cleaned_data['is_polyteacher'] = False
            cleaned_data['teaching_courses'] = Course.objects.none()
            cleaned_data['teaching_grades'] = Grade.objects.none()
            cleaned_data['teaching_sections'] = Section.objects.none()

        return cleaned_data

    def _sync_tutor_section(self, user, previous_section_id):
        current_section_id = user.teaching_section_id if user.role == 'teacher' else None

        if previous_section_id and previous_section_id != current_section_id:
            Section.objects.filter(id=previous_section_id, tutor_teacher=user).update(tutor_teacher=None)

        if current_section_id:
            Section.objects.filter(id=current_section_id).update(tutor_teacher=user)

    def save(self, commit=True):
        previous_section_id = None
        if self.instance.pk:
            previous_section_id = (
                User.objects.filter(pk=self.instance.pk)
                .values_list('teaching_section_id', flat=True)
                .first()
            )

        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            user.set_password(password)

        if commit:
            user.save()
            user.teaching_courses.set(self.cleaned_data.get('teaching_courses', []))
            user.teaching_grades.set(self.cleaned_data.get('teaching_grades', []))
            user.teaching_sections.set(self.cleaned_data.get('teaching_sections', []))
            self._sync_tutor_section(user, previous_section_id)

            active_year = AcademicYear.objects.filter(is_active=True).order_by('-year').first()
            if user.role == 'teacher' and active_year:
                if user.teaching_section_id:
                    for course in Course.objects.order_by('name'):
                        TeacherCourseAssignment.objects.get_or_create(
                            teacher=user,
                            course=course,
                            section=user.teaching_section,
                            academic_year=active_year,
                            defaults={'grade': user.teaching_grade},
                        )

                if user.is_polyteacher:
                    for course in user.teaching_courses.all():
                        for section in user.teaching_sections.select_related('grade').all():
                            TeacherCourseAssignment.objects.get_or_create(
                                teacher=user,
                                course=course,
                                grade=section.grade,
                                section=section,
                                academic_year=active_year,
                                defaults={},
                            )

        return user


class SchoolConfigForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ['name', 'logo', 'address', 'phone', 'email']


class UserUpdateForm(UserCreateForm):
    password1 = forms.CharField(
        label='Contrasena',
        widget=forms.PasswordInput(attrs={'placeholder': 'Nueva contrasena (dejar en blanco para no cambiar)'}),
        help_text='Opcional. Si se deja en blanco, se mantendra la contrasena actual.',
        required=False,
    )
    password2 = forms.CharField(
        label='Confirmar contrasena',
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirmar nueva contrasena'}),
        help_text='Repite la nueva contrasena si deseas cambiarla.',
        required=False,
    )

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1:
            if not password2:
                raise forms.ValidationError('Debes confirmar la nueva contrasena.')
            if password1 != password2:
                raise forms.ValidationError('Las contrasenas no coinciden.')
            if len(password1) < 8:
                raise forms.ValidationError('La contrasena debe tener al menos 8 caracteres.')
        return password2


class SchoolIdentityForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ['name', 'ruc', 'logo', 'address', 'phone', 'email']


class SchoolBusinessForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ['pension_price', 'enrollment_price', 'supplies_price']
        widgets = {
            'pension_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'stat-price-input'}),
            'enrollment_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'stat-price-input'}),
            'supplies_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'stat-price-input'}),
        }


class SelfProfileForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Nueva contrasena',
        widget=forms.PasswordInput(attrs={'placeholder': 'Dejar en blanco para no cambiar'}),
        required=False,
        help_text='Opcional. Al menos 8 caracteres.',
    )
    password2 = forms.CharField(
        label='Confirmar nueva contrasena',
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirmar nueva contrasena'}),
        required=False,
    )

    class Meta:
        model = User
        fields = ['profile_picture', 'first_name', 'last_name', 'email', 'phone']
        labels = {
            'profile_picture': 'Foto de perfil',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo electronico',
            'phone': 'Telefono',
        }

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1:
            if not p2:
                raise forms.ValidationError('Debes confirmar la nueva contrasena.')
            if p1 != p2:
                raise forms.ValidationError('Las contrasenas no coinciden.')
            if len(p1) < 8:
                raise forms.ValidationError('La contrasena debe ser de al menos 8 caracteres.')
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        p1 = self.cleaned_data.get('password1')
        if p1:
            user.set_password(p1)
        if commit:
            user.save()
        return user
