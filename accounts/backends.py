from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class UsernameOrEmailBackend(ModelBackend):
    """Authenticate using username (case-insensitive) or email."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if password is None:
            return None

        identifier = (username or kwargs.get('username') or '').strip()
        if not identifier:
            return None

        user_model = get_user_model()
        candidates = user_model.objects.filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier)
        )

        for user in candidates:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        return None
