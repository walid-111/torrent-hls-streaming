from rest_framework import serializers
from .models import User
import re

def password_error(value):
    # same rules everywhere a password is set (register, reset, profile)
    if not value or len(value) < 8:
        return "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', value):
        return "Password must contain at least one uppercase letter"
    if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', value):
        return "Password must contain at least one special character"
    return None


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password']

    def validate_password(self, value):
        error = password_error(value)
        if error:
            raise serializers.ValidationError(error)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'bio', 'avatar', 'preferred_language']
        read_only_fields = ['id']

    def validate_avatar(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Image too large (max 5MB)")
        if not value.content_type.startswith('image/'):
            raise serializers.ValidationError("File must be an image")
        return value