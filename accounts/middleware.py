from .models import ActivityLog


class ActivityLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and request.user.is_authenticated:
            ActivityLog.objects.create(
                user=request.user,
                action='user_action',
                path=request.path,
                method=request.method,
                ip_address=self._get_client_ip(request),
            )
        return response

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')
