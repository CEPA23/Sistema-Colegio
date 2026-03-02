from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib import messages
from .models import Event
from .forms import EventForm
from accounts.decorators import role_required
from django.utils import timezone

@login_required
def event_calendar(request):
    """Muestra el calendario principal."""
    is_director = request.user.role == 'director' or request.user.is_superuser
    upcoming = get_upcoming_events(days=3)
    
    # Contar eventos del mes actual
    now = timezone.now()
    month_events_count = Event.objects.filter(
        start_date__year=now.year, 
        start_date__month=now.month
    ).count()
    
    context = {
        'is_director': is_director,
        'today': now.strftime('%Y-%m-%d'),
        'upcoming_events': upcoming,
        'month_events_count': month_events_count
    }
    return render(request, 'events/calendar.html', context)

@role_required('director')
def event_create(request):
    """Vista para crear eventos."""
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            # Manejar la lógica de fecha de fin
            if not form.cleaned_data.get('has_end_date'):
                event.end_date = None
            event.save()
            messages.success(request, f"Evento '{event.title}' guardado correctamente.")
            return redirect('events:calendar')
    else:
        form = EventForm()
    
    return render(request, 'events/event_form.html', {'form': form})

@login_required
def event_json(request):
    """Devuelve eventos en formato JSON para FullCalendar."""
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    
    events = Event.objects.all()
    
    if start_str and end_str:
        # Extraer solo la parte YYYY-MM-DD para evitar errores de validación con ISO strings
        try:
            start_date = start_str.split('T')[0]
            end_date = end_str.split('T')[0]
            
            from django.db.models import Q
            events = events.filter(
                Q(start_date__lte=end_date) & 
                (Q(end_date__isnull=True, start_date__gte=start_date) | 
                 Q(end_date__isnull=False, end_date__gte=start_date))
            )
        except (IndexError, ValueError):
            pass # Si el formato es inesperado, devolvemos todo o manejamos el error
        
    data = []
    for event in events:
        event_dict = {
            'id': event.id,
            'title': event.title,
            'start': event.start_date.strftime('%Y-%m-%d'),
            'description': event.description or '',
            'allDay': True,
        }
        
        if event.end_date:
            from datetime import timedelta
            # FullCalendar end date is exclusive
            inclusive_end = event.end_date + timedelta(days=1)
            event_dict['end'] = inclusive_end.strftime('%Y-%m-%d')
            event_dict['backgroundColor'] = '#4f46e5' # Indigo
            event_dict['borderColor'] = '#4f46e5'
        else:
            event_dict['backgroundColor'] = '#10b981' # Emerald
            event_dict['borderColor'] = '#10b981'
            
        data.append(event_dict)
        
    return JsonResponse(data, safe=False)

def get_upcoming_events(days=3):
    """Helper para obtener eventos próximos en los siguientes N días."""
    from datetime import date, timedelta
    today = date.today()
    limit = today + timedelta(days=days)
    
    # Eventos que inician entre hoy y el límite
    return Event.objects.filter(start_date__gte=today, start_date__lte=limit).order_by('start_date')
