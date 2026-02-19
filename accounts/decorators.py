from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def role_required(*allowed_roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser or request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            messages.error(request, "No tienes permisos para acceder a esta seccion.")
            return redirect('dashboard')

        return _wrapped_view

    return decorator
