from django.urls import path
from core.views import (
    HealthCheckView,
    ReadinessCheckView,
    AuthLoginView,
    AuthMeView,
    AuditLogListView,
)

urlpatterns = [
    # Probes
    path('healthz/', HealthCheckView.as_view(), name='healthz'),
    path('readyz/', ReadinessCheckView.as_view(), name='readyz'),

    # Auth & Identity
    path('auth/login/', AuthLoginView.as_view(), name='core-login'),
    path('auth/me/', AuthMeView.as_view(), name='core-me'),

    # Audit Trail
    path('audit-logs/', AuditLogListView.as_view(), name='core-audit-logs'),
]
