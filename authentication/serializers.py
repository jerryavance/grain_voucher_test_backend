# authentication/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from authentication.models import UserProfile, OTPVerification
from authentication.helpers import normalize_phone_number, validate_phone_number
from authentication.backends import PhoneOTPBackend
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
import re

from hubs.models import Hub  # Import Hub for UserSerializer

class OTPRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=17)
    purpose = serializers.ChoiceField(choices=['registration', 'login', 'phone_verification'], default='registration')
    
    def validate_phone_number(self, value):
        return validate_phone_number(value)
    
    def validate(self, attrs):
        phone_number = attrs.get('phone_number')
        purpose = attrs.get('purpose')
        
        user_exists = get_user_model().objects.filter(phone_number=phone_number).exists()
        
        if purpose in ['login'] and not user_exists:
            raise serializers.ValidationError('No account found. Register first.')
        elif purpose == 'registration' and user_exists:
            raise serializers.ValidationError('Account exists. Login instead.')
        
        return attrs

class OTPVerificationSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=17)
    otp_code = serializers.CharField(max_length=6, min_length=4)
    purpose = serializers.ChoiceField(choices=['registration', 'login', 'phone_verification'], default='registration')
    
    def validate_phone_number(self, value):
        return normalize_phone_number(value)
    
    def validate(self, attrs):
        phone_number = attrs.get('phone_number')
        otp_code = attrs.get('otp_code')
        purpose = attrs.get('purpose')
        
        try:
            otp_record = OTPVerification.objects.get(
                phone_number=phone_number,
                purpose=purpose,
                is_verified=False,
                expires_at__gt=timezone.now()
            )
        except OTPVerification.DoesNotExist:
            raise serializers.ValidationError('Invalid or expired OTP')
        
        is_valid, message = otp_record.verify(otp_code)
        if not is_valid:
            raise serializers.ValidationError(message)
        
        attrs['otp_record'] = otp_record
        return attrs

class UserRegistrationSerializer(serializers.ModelSerializer):
    otp_code = serializers.CharField(max_length=6, min_length=4, write_only=True)
    accept_terms = serializers.BooleanField(write_only=True)
    
    class Meta:
        model = get_user_model()
        fields = [
            'phone_number', 'otp_code', 'first_name', 'last_name', 
            'role', 'accept_terms'
        ]
    
    def validate_phone_number(self, value):
        return validate_phone_number(value)
    
    def validate(self, attrs):
        otp_code = attrs.get('otp_code')
        phone_number = attrs.get('phone_number')
        
        try:
            otp_record = OTPVerification.objects.get(
                phone_number=phone_number,
                otp_code=otp_code,
                purpose='registration',
                is_verified=False,
                expires_at__gt=timezone.now()
            )
        except OTPVerification.DoesNotExist:
            raise serializers.ValidationError('Invalid or expired OTP')
        
        is_valid, message = otp_record.verify(otp_code)
        if not is_valid:
            raise serializers.ValidationError(message)
        
        if not attrs.get('accept_terms'):
            raise serializers.ValidationError('You must accept the terms and conditions')
        
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('otp_code')
        validated_data.pop('accept_terms')
        validated_data['phone_verified'] = True
        return super().create(validated_data)

class PhoneLoginSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=17)
    otp_code = serializers.CharField(max_length=6, min_length=4)
    
    def validate_phone_number(self, value):
        return normalize_phone_number(value)
    
    def validate(self, attrs):
        phone_number = attrs.get('phone_number')
        otp_code = attrs.get('otp_code')
        
        user = PhoneOTPBackend().authenticate(
            request=self.context.get('request'),
            phone_number=phone_number,
            otp_code=otp_code
        )
        if not user:
            raise serializers.ValidationError('Invalid credentials')
        
        attrs['user'] = user
        return attrs

class UserSerializer(serializers.ModelSerializer):
    hubs = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = [
            'id', 'phone_number', 'first_name', 'last_name', 
            'role', 'is_superuser', 'profile', 'hubs'
        ]
        read_only_fields = ['id', 'phone_verified']

    def get_profile(self, obj):
        try:
            return {'location': obj.profile.location}
        except UserProfile.DoesNotExist:
            return {'location': ''}

    def get_hubs(self, obj):
        return [
            {
                'id': str(m.hub.id),
                'name': m.hub.name,
                'slug': m.hub.slug,
                'role': m.role,
                'status': m.status,
            }
            for m in obj.hub_memberships.filter(status='active')
        ]
