from django.contrib.auth.base_user import BaseUserManager
from django.core.exceptions import ValidationError
from authentication.helpers import normalize_phone_number, validate_phone_number

class CustomUserManager(BaseUserManager):
    def _validate_phone(self, phone_number):
        return validate_phone_number(phone_number)
    
    def create_user(self, phone_number, role='farmer', **extra_fields):
        if not phone_number:
            raise ValueError('Phone number is required')
        
        normalized_phone = self._validate_phone(phone_number)
        
        if not hasattr(self, 'model') or self.model is None:
            from authentication.models import GrainUser  # Lazy import to avoid circular import
            self.model = GrainUser
        
        if self.model.objects.filter(phone_number=normalized_phone).exists():
            raise ValidationError('A user with this phone number already exists')
        
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', role)
        
        user = self.model(
            phone_number=normalized_phone,
            **extra_fields
        )
        
        user.set_unusable_password()
        user.save(using=self._db)
        return user
    
    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'super_admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Super user must have is_staff = True')
        
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Super user must have is_superuser = True')
        
        if not password:
            raise ValueError('Superuser must have a password')
        
        user = self.create_user(
            phone_number=phone_number, 
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def get_by_natural_key(self, username):
        normalized_phone = normalize_phone_number(username)
        return self.get(phone_number=normalized_phone)