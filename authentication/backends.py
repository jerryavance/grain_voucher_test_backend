from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from authentication.models import OTPVerification
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class PhoneOTPBackend(ModelBackend):
    def authenticate(self, request, phone_number=None, otp_code=None):
        if phone_number is None or otp_code is None:
            return None
            
        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return None
        
        try:
            otp = OTPVerification.objects.filter(
                phone_number=phone_number,
                purpose='login',
                is_verified=False
            ).latest('created_at')
            
            is_valid, error_message = otp.verify(otp_code)
            
            if is_valid:
                otp.is_verified = True
                otp.save()
                logger.info(f"User {phone_number} ({user.role}) authenticated")
                return user
            
            return None
            
        except OTPVerification.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


def authenticate_with_otp(phone_number, otp_code, purpose='login'):
    UserModel = get_user_model()
    
    try:
        user_instance = UserModel()
        normalized_phone = user_instance.normalize_phone_number(phone_number)
        
        try:
            user = UserModel.objects.get(phone_number=normalized_phone)
        except UserModel.DoesNotExist:
            return None, "No account found with this phone number"
        
        try:
            otp_record = OTPVerification.objects.filter(
                phone_number=normalized_phone,
                purpose=purpose,
                is_verified=False
            ).latest('created_at')
        except OTPVerification.DoesNotExist:
            return None, f"No valid OTP found for {purpose}. Please request a new OTP."
        
        is_valid, error_message = otp_record.verify(otp_code)
        
        if is_valid:
            if not user.is_active:
                return None, "User account is disabled"
            
            otp_record.is_verified = True
            otp_record.save()
            
            logger.info(f"Successful OTP authentication for {normalized_phone} ({purpose})")
            return user, None
        else:
            logger.warning(f"Failed OTP authentication for {normalized_phone} ({purpose}): {error_message}")
            return None, error_message
            
    except Exception as e:
        logger.error(f"Error in OTP authentication: {e}")
        return None, "Authentication failed. Please try again."


def check_authentication_rate_limit(request, identifier, limit=5, window_minutes=15):
    try:
        from django.core.cache import cache
        from django.utils import timezone
        from datetime import timedelta
        
        ip_key = f"auth_attempts_{request.META.get('REMOTE_ADDR', 'unknown')}"
        identifier_key = f"auth_attempts_{identifier}"
        
        now = timezone.now()
        window_seconds = window_minutes * 60
        
        ip_data = cache.get(ip_key, {'count': 0, 'reset_time': now})
        identifier_data = cache.get(identifier_key, {'count': 0, 'reset_time': now})
        
        if now > ip_data['reset_time']:
            ip_data = {'count': 0, 'reset_time': now + timedelta(seconds=window_seconds)}
        if now > identifier_data['reset_time']:
            identifier_data = {'count': 0, 'reset_time': now + timedelta(seconds=window_seconds)}
        
        if ip_data['count'] >= (limit * 3) or identifier_data['count'] >= limit:
            return False, 0, max(ip_data['reset_time'], identifier_data['reset_time'])
        
        return True, min(limit - identifier_data['count'], (limit * 3) - ip_data['count']), None
        
    except Exception as e:
        logger.error(f"Error checking rate limits: {e}")
        return True, limit, None


def record_authentication_attempt(request, identifier, success=False):
    try:
        from django.core.cache import cache
        from django.utils import timezone
        from datetime import timedelta
        
        ip_key = f"auth_attempts_{request.META.get('REMOTE_ADDR', 'unknown')}"
        identifier_key = f"auth_attempts_{identifier}"
        
        now = timezone.now()
        window_seconds = 15 * 60
        
        ip_data = cache.get(ip_key, {'count': 0, 'reset_time': now + timedelta(seconds=window_seconds)})
        if now > ip_data['reset_time']:
            ip_data = {'count': 0, 'reset_time': now + timedelta(seconds=window_seconds)}
        ip_data['count'] += 1
        cache.set(ip_key, ip_data, window_seconds)
        
        identifier_data = cache.get(identifier_key, {'count': 0, 'reset_time': now + timedelta(seconds=window_seconds)})
        if now > identifier_data['reset_time']:
            identifier_data = {'count': 0, 'reset_time': now + timedelta(seconds=window_seconds)}
        identifier_data['count'] += 1
        cache.set(identifier_key, identifier_data, window_seconds)
        
        logger.info(f"Recorded authentication attempt for {identifier} (success: {success})")
        
    except Exception as e:
        logger.error(f"Error recording authentication attempt: {e}")