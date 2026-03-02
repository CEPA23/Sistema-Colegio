from django import forms
from .models import Event

class EventForm(forms.ModelForm):
    has_end_date = forms.BooleanField(
        required=False, 
        initial=False,
        label="¿Es un evento de rango de fechas?",
        widget=forms.CheckboxInput(attrs={'class': 'custom-control-input'})
    )

    class Meta:
        model = Event
        fields = ['title', 'description', 'start_date', 'has_end_date', 'end_date']
        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'Ej: Reunión de Padres de Familia',
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Escribe una breve descripción...',
                'rows': 3,
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
            }),
        }
        labels = {
            'title': 'Nombre del Evento',
            'description': 'Detalles adicionales',
            'start_date': 'Fecha de Inicio',
            'end_date': 'Fecha de Finalización',
        }

    def clean(self):
        cleaned_data = super().clean()
        has_end_date = cleaned_data.get('has_end_date')
        end_date = cleaned_data.get('end_date')
        start_date = cleaned_data.get('start_date')

        if not has_end_date:
            cleaned_data['end_date'] = None
        elif not end_date:
            self.add_error('end_date', 'Debe ingresar una fecha de fin.')
        elif end_date and start_date and end_date < start_date:
            self.add_error('end_date', 'La fecha de fin no puede ser anterior a la fecha de inicio.')
        
        return cleaned_data
