from .models import School


def school_context(request):
    system_school = School.objects.order_by('id').first()
    return {
        'system_school': system_school,
    }
