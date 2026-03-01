from django import forms
from django.db.models import Q

from academic.models import Course, Grade, Section
from enrollment.models import Enrollment

from inventory.models import Product
from .models import Fee, Payment


class PaymentRegistrationForm(forms.Form):
    student_name = forms.CharField(
        required=True,
        label='Alumno',
        widget=forms.TextInput(attrs={'placeholder': 'Escribe el nombre del alumno'})
    )
    enrollment_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    concept = forms.ChoiceField(choices=Fee.CONCEPT_CHOICES, label='Concepto')
    pension_month = forms.ChoiceField(
        required=False,
        choices=[('', 'Selecciona un mes')] + [(str(k), v) for k, v in Fee.MONTH_CHOICES],
        label='Mes de pension'
    )

    inventory_product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True),
        required=False,
        label='Producto de Inventario',
        empty_label="Selecciona un producto"
    )
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0.01, label='Monto a pagar')
    method = forms.ChoiceField(choices=Payment.METHOD_CHOICES, label='Metodo de pago')
    proof_image = forms.FileField(required=False, label='Captura de transferencia / Yape-Plin')
    comment = forms.CharField(
        required=False,
        label='Comentario',
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Comentario opcional antes de registrar el pago'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['inventory_product'].queryset = Product.objects.filter(is_active=True).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        student_name = cleaned_data.get('student_name')
        enrollment_id = cleaned_data.get('enrollment_id')
        concept = cleaned_data.get('concept')
        pension_month = cleaned_data.get('pension_month')
        method = cleaned_data.get('method')
        proof_image = cleaned_data.get('proof_image')

        enrollment = None
        if enrollment_id:
            enrollment = Enrollment.objects.select_related('student', 'section__grade', 'academic_year').filter(
                id=enrollment_id
            ).first()

        if not enrollment and student_name:
            matches = Enrollment.objects.select_related('student', 'section__grade', 'academic_year').filter(
                Q(student__first_name__icontains=student_name)
                | Q(student__last_name__icontains=student_name)
            ).order_by('-academic_year__year', 'student__last_name')
            if matches.count() == 1:
                enrollment = matches.first()

        if not enrollment:
            self.add_error('student_name', 'Selecciona un alumno valido de las sugerencias.')
        else:
            cleaned_data['enrollment'] = enrollment

        if concept == Fee.CONCEPT_PENSION and not pension_month:
            self.add_error('pension_month', 'Debes seleccionar el mes para una pension.')

        if concept != Fee.CONCEPT_PENSION:
            cleaned_data['pension_month'] = None

        if method in (Payment.METHOD_TRANSFER, Payment.METHOD_YAPE_PLIN) and not proof_image:
            self.add_error('proof_image', 'Debes adjuntar la captura del pago.')

        if concept == Fee.CONCEPT_BOOK:
            if not cleaned_data.get('inventory_product'):
                 self.add_error('inventory_product', 'Debes seleccionar el libro desde el inventario.')
        
        if concept in [Fee.CONCEPT_BAND_UNIFORM, Fee.CONCEPT_SCHOOL_UNIFORM, Fee.CONCEPT_PRODUCT]:
            if not cleaned_data.get('inventory_product'):
                self.add_error('inventory_product', 'Debes seleccionar un producto del inventario.')

        return cleaned_data


class QuickEnrollmentForm(forms.Form):
    dni = forms.CharField(max_length=8, min_length=8, label='DNI')
    first_name = forms.CharField(max_length=150, label='Nombres del alumno')
    last_name = forms.CharField(max_length=150, label='Apellidos del alumno')
    birth_date = forms.DateField(
        label='Fecha de nacimiento',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    address = forms.CharField(max_length=500, label='Direccion')
    parent_name = forms.CharField(max_length=150, label='Apoderado principal')
    parent_phone = forms.CharField(max_length=15, label='Telefono del apoderado')
    father_name = forms.CharField(max_length=150, label='Nombre del padre')
    father_phone = forms.CharField(max_length=15, label='Telefono del padre')
    mother_name = forms.CharField(max_length=150, label='Nombre de la madre')
    mother_phone = forms.CharField(max_length=15, label='Telefono de la madre')
    grade = forms.ModelChoiceField(queryset=Grade.objects.order_by('name'), label='Grado')
    section = forms.ModelChoiceField(queryset=Section.objects.none(), label='Seccion')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['section'].queryset = Section.objects.select_related('grade').order_by('grade__name', 'name')

        grade = None
        if self.is_bound:
            grade = self.data.get('grade')
        if grade:
            self.fields['section'].queryset = Section.objects.filter(grade_id=grade).order_by('name')

    def clean_dni(self):
        dni = (self.cleaned_data.get('dni') or '').strip()
        if not dni.isdigit():
            raise forms.ValidationError('El DNI debe contener solo numeros.')
        return dni

    def clean_parent_phone(self):
        return (self.cleaned_data.get('parent_phone') or '').strip()

    def clean_father_phone(self):
        return (self.cleaned_data.get('father_phone') or '').strip()

    def clean_mother_phone(self):
        return (self.cleaned_data.get('mother_phone') or '').strip()

    def clean(self):
        cleaned_data = super().clean()
        grade = cleaned_data.get('grade')
        section = cleaned_data.get('section')
        if grade and section and section.grade_id != grade.id:
            self.add_error('section', 'La seccion no pertenece al grado seleccionado.')
        return cleaned_data
