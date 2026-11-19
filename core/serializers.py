import re
from rest_framework import serializers
from django.contrib.auth import authenticate
from core.models import User, UserRole, AuditLog


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'role_display', 'phone_number', 'gstin', 'license_number',
            'company_name', 'is_verified', 'assigned_credit_limit',
            'credit_period_days', 'date_joined'
        ]
        read_only_fields = ['id', 'date_joined']


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'first_name', 'last_name',
            'role', 'phone_number', 'gstin', 'license_number',
            'company_name', 'assigned_credit_limit', 'credit_period_days'
        ]

    def validate_gstin(self, value):
        if value:
            # 15-character Indian GSTIN format: 2 digits state + 10 char PAN + 1 entity + Z + 1 check digit
            gstin_regex = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
            if not re.match(gstin_regex, value.strip().upper()):
                raise serializers.ValidationError("Invalid Indian GSTIN format. Expected 15-character format (e.g. 27AABCU9603R1ZM).")
        return value.strip().upper() if value else None

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')

        if username and password:
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError("Invalid credentials provided.")
            if not user.is_active:
                raise serializers.ValidationError("User account is disabled.")
            attrs['user'] = user
            return attrs
        raise serializers.ValidationError("Both username and password are required.")


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            'id', 'timestamp', 'actor_username', 'actor_role',
            'ip_address', 'user_agent', 'action', 'entity_type', 'entity_id',
            'pre_change_snapshot', 'post_change_snapshot', 'delta', 'metadata'
        ]
        read_only_fields = fields
