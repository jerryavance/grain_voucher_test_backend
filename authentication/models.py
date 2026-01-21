from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.exceptions import ValidationError
from authentication.helpers import normalize_phone_number, validate_phone_number
from authentication.managers import CustomUserManager
from utils.constants import USER_ROLES, USER_ROLE_FARMER
from datetime import timedelta
import uuid

class GrainUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = None
    phone_number = models.CharField(max_length=17, unique=True)
    role = models.CharField(max_length=20, choices=USER_ROLES, default=USER_ROLE_FARMER)
    # Remove this line: hub = models.ForeignKey(Hub, on_delete=models.SET_NULL, null=True, blank=True, related_name='members',help_text="The hub this user is associated with.")
    phone_verified = models.BooleanField(default=False)
    accept_terms = models.BooleanField(default=False)
    
    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []
    
    objects = CustomUserManager()

    class Meta:
        ordering = ['phone_number']
        indexes = [
            models.Index(fields=['phone_number']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.phone_number}) - {self.role}"
    
    @property
    def active_hubs(self):
        """Get all hubs where user has active membership"""
        from hubs.models import Hub  # lazy import to avoid circular import
        return Hub.objects.filter(
            memberships__user=self,
            memberships__status='active'
        ).distinct()
    
    @property
    def primary_hub(self):
        """Get user's primary hub (first active membership or None)"""
        from hubs.models import Hub  # lazy import to avoid circular import
        return self.active_hubs.first()
    
    def is_member_of_hub(self, hub):
        """Check if user is an active member of a specific hub"""
        return self.hub_memberships.filter(
            hub=hub, 
            status='active'
        ).exists()
    
    def get_role_in_hub(self, hub):
        """Get user's role in a specific hub"""
        membership = self.hub_memberships.filter(
            hub=hub, 
            status='active'
        ).first()
        return membership.role if membership else None

class UserProfile(models.Model):
    user = models.OneToOneField(GrainUser, on_delete=models.CASCADE, related_name='profile')
    location = models.CharField(max_length=255, blank=True, default='')  # Added default
    gender = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"Profile for {self.user.phone_number}"

class OTPVerification(models.Model):
    phone_number = models.CharField(max_length=17)
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=[('registration', 'Registration'), ('login', 'Login'), ('phone_verification', 'Phone Verification')])
    expires_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['phone_number', 'purpose']),
        ]

    def save(self, *args, **kwargs):
        self.phone_number = normalize_phone_number(self.phone_number)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=5)
        super().save(*args, **kwargs)

    @classmethod
    def generate_otp_code(cls, phone_number):
        import secrets  # Added import
        return str(secrets.randbelow(900000) + 100000)  # Secure random

    def verify(self, code):
        if self.is_verified:
            return False, "OTP already verified"
        if self.attempts >= 3:
            return False, "Maximum attempts exceeded"
        if timezone.now() > self.expires_at:
            return False, "OTP has expired"
        if code != self.otp_code:
            self.attempts += 1
            self.save()
            return False, "Invalid OTP"
        
        self.is_verified = True
        self.attempts = 0
        self.save()
        return True, "OTP verified successfully"

class UserActivity(models.Model):
    user = models.ForeignKey(GrainUser, on_delete=models.CASCADE)
    activity_type = models.CharField(max_length=50)
    description = models.TextField()
    points_earned = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.phone_number} - {self.activity_type}"

class PhoneVerificationLog(models.Model):
    phone_number = models.CharField(max_length=17)
    purpose = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=[('sent', 'Sent'), ('failed', 'Failed'), ('verified', 'Verified')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['phone_number', 'created_at']),
        ]
        ordering = ['-created_at']