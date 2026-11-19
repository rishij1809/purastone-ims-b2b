import time
from datetime import datetime, timezone
from django.db import connection
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from core.models import User, AuditLog, UserRole
from core.serializers import UserSerializer, UserCreateSerializer, LoginSerializer, AuditLogSerializer
from core.permissions import IsAdminOrProprietor, HasRolePermission


class HealthCheckView(APIView):
    """
    Liveness probe: verifies the application worker process is alive and accepting traffic.
    Used by Nginx, AWS ALB, Docker Compose and Kubernetes.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "status": "healthy",
            "service": "purastone-skincare-erp",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_check": "OK"
        }, status=status.HTTP_200_OK)


class ReadinessCheckView(APIView):
    """
    Readiness probe: validates connectivity to primary PostgreSQL database and Redis cache.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        checks = {}
        is_ready = True

        # 1. Database Connectivity Check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                row = cursor.fetchone()
                if row and row[0] == 1:
                    checks["database"] = "CONNECTED"
                else:
                    checks["database"] = "UNEXPECTED_RESPONSE"
                    is_ready = False
        except Exception as e:
            checks["database"] = f"ERROR: {str(e)}"
            is_ready = False

        # 2. Cache Connectivity Check
        try:
            cache_key = f"_health_probe_{int(time.time())}"
            cache.set(cache_key, "1", timeout=5)
            val = cache.get(cache_key)
            if val == "1":
                checks["cache"] = "CONNECTED"
            else:
                checks["cache"] = "DEGRADED"
        except Exception as e:
            checks["cache"] = f"ERROR: {str(e)}"

        status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response({
            "status": "ready" if is_ready else "not_ready",
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, status=status_code)


class AuthLoginView(APIView):
    """
    Authenticates user credentials and returns full RBAC profile and authorization scopes.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        user_data = UserSerializer(user).data
        return Response({
            "status": "success",
            "message": f"Authenticated successfully as {user.username}",
            "user": user_data,
            "roles": {
                "primary": user.role,
                "is_admin": user.is_admin_or_proprietor,
                "is_sales": user.is_sales_team,
                "is_warehouse": user.is_warehouse_supervisor,
                "is_accounting": user.is_accounting_staff,
                "is_retailer": user.is_primary_client_retailer,
                "is_service_provider": user.is_service_provider,
            }
        }, status=status.HTTP_200_OK)


class AuthMeView(APIView):
    """
    Returns current authenticated user profile, permissions, and active role.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        user_data = UserSerializer(user).data
        return Response({
            "user": user_data,
            "roles": {
                "primary": user.role,
                "is_admin": user.is_admin_or_proprietor,
                "is_sales": user.is_sales_team,
                "is_warehouse": user.is_warehouse_supervisor,
                "is_accounting": user.is_accounting_staff,
                "is_retailer": user.is_primary_client_retailer,
                "is_service_provider": user.is_service_provider,
            }
        }, status=status.HTTP_200_OK)


class AuditLogListView(generics.ListAPIView):
    """
    Immutable System Audit Log Explorer.
    Accessible only to Admin/Proprietor and Accounting Staff.
    Supports filtering by action, entity_type, entity_id, actor, and date.
    """
    serializer_class = AuditLogSerializer
    permission_classes = [HasRolePermission.with_roles(
        UserRole.ADMIN_PROPRIETOR,
        UserRole.ACCOUNTING_STAFF,
    )]

    def get_queryset(self):
        qs = AuditLog.objects.all().order_by('-timestamp')
        action = self.request.query_params.get('action')
        entity_type = self.request.query_params.get('entity_type')
        entity_id = self.request.query_params.get('entity_id')
        actor = self.request.query_params.get('actor')

        if action:
            qs = qs.filter(action=action)
        if entity_type:
            qs = qs.filter(entity_type=entity_type)
        if entity_id:
            qs = qs.filter(entity_id=str(entity_id))
        if actor:
            qs = qs.filter(actor_username__icontains=actor)

        return qs[:200]
