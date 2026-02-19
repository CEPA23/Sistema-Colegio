from django import forms
from django.db.models import Q

from academic.models import Course
from enrollment.models import Enrollment

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
    course = forms.ModelChoiceField(
        queryset=Course.objects.all().order_by('name'),
        required=False,
        label='Libro de curso',
        empty_label="Selecciona un curso (para libros)"
    )
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0.01, label='Monto a pagar')
    method = forms.ChoiceField(choices=Payment.METHOD_CHOICES, label='Metodo de pago')
    proof_image = forms.FileField(required=False, label='Captura de transferencia / Yape-Plin')
    comment = forms.CharField(
        required=False,
        label='Comentario',
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Comentario opcional antes de registrar el pago'})
    )

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

        if concept == 'libro' and not cleaned_data.get('course'):
            self.add_error('course', 'Debes seleccionar el libro/curso correspondiente.')

        return cleaned_data
