import contextvars
from django.utils.deprecation import MiddlewareMixin

# Thread-safe and async-safe request context storage
_current_audit_context = contextvars.ContextVar("purastone_audit_context", default={})


def get_current_audit_context() -> dict:
    """
    Retrieves the audit context for the active request thread/task.
    Returns a dict containing 'user', 'ip_address', 'user_agent', and 'path'.
    """
    return _current_audit_context.get()


def get_client_ip(request) -> str:
    """
    Extracts the client's public IP address, respecting reverse proxies and ALBs.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # First IP in the comma-separated chain is the client IP
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip or "127.0.0.1"


class AuditContextMiddleware(MiddlewareMixin):
    """
    Automated Middleware that captures actor details, client IP, and user-agent
    into an isolated contextvar for seamless audit logging across signals and models.
    """

    def process_request(self, request):
        user = getattr(request, 'user', None)
        ip = get_client_ip(request)
        ua = request.META.get('HTTP_USER_AGENT', '')
        path = request.path

        ctx = {
            'user': user if (user and user.is_authenticated) else None,
            'ip_address': ip,
            'user_agent': ua,
            'path': path,
            'method': request.method,
        }
        _current_audit_context.set(ctx)

    def process_response(self, request, response):
        # Reset context on completion of response cycle
        _current_audit_context.set({})
        return response

    def process_exception(self, request, exception):
        # Reset context on unhandled exception
        _current_audit_context.set({})
        return None
