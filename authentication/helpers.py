import uuid
from django.db.models import Model
import re
from django.core.exceptions import ValidationError


def get_file_path(instance: Model, filename: str) -> str:
    extension = filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{extension}"
    
    # Multi-tenant: Prefix with hub slug if applicable
    hub_prefix = ''
    if hasattr(instance, 'hub') and instance.hub:
        hub_prefix = f"{instance.hub.slug}/"
    elif hasattr(instance, 'user') and instance.user.hub:
        hub_prefix = f"{instance.user.hub.slug}/"
    
    return f"{instance._meta.db_table}/{hub_prefix}{filename}"


def normalize_phone_number(phone):
    """
    Normalize phone number to E.164 format +XXXXXXXXXXXX
    """
    if not phone:
        return phone
        
    # Remove non-digits except +
    phone = ''.join(char for char in phone if char.isdigit() or char == '+')
    
    # Add + if missing
    if not phone.startswith('+'):
        phone = '+' + phone
        
    return phone


def validate_phone_number(phone_number):
    """
    Validate if phone number is a valid international number
    """
    if not phone_number:
        raise ValidationError('Phone number is required')
        
    normalized_phone = normalize_phone_number(phone_number)
    general_pattern = r'^\+\d{10,15}$'  # General international format
    
    if not re.match(general_pattern, normalized_phone):
        raise ValidationError(
            'Phone number must be a valid international number (e.g., +256772123456)'
        )
    
    return normalized_phone