from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from authentication.models import UserProfile, UserActivity
from django.contrib.auth.signals import user_logged_in
import logging
from datetime import date

logger = logging.getLogger(__name__)

@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        try:
            UserProfile.objects.get_or_create(user=instance, defaults={'location': ''})
            logger.info(f"Profile created for user {instance.phone_number} ({instance.role})")
            
            if instance.role == 'farmer' and instance.phone_verified:
                UserActivity.objects.create(
                    user=instance,
                    activity_type='profile_update',
                    description=f'Welcome, {instance.first_name}! View hubs and deposit grain.',
                    points_earned=10
                )
        except Exception as e:
            logger.error(f"Error creating profile: {e}")

@receiver(post_save, sender=get_user_model())
def phone_verification_activity(sender, instance, created, **kwargs):
    if not created and instance.phone_verified:
        try:
            existing_verification = UserActivity.objects.filter(
                user=instance,
                activity_type='phone_verified',
            ).exists()
            
            if not existing_verification:
                UserActivity.objects.create(
                    user=instance,
                    activity_type='phone_verified',
                    description='Phone number verified',
                    points_earned=15
                )
        except Exception as e:
            logger.error(f"Error creating phone verification activity: {e}")

@receiver(user_logged_in, sender=get_user_model())
def log_user_login(sender, request, user, **kwargs):
    try:
        today = date.today()
        
        # Log basic login
        UserActivity.objects.create(
            user=user,
            activity_type='login',
            description=f'{user} logged in'
        )
        
        # Log daily login bonus
        today_login = UserActivity.objects.filter(
            user=user,
            activity_type='login',
            description='Daily login',
            created_at__date=today
        ).exists()
        
        if not today_login:
            UserActivity.objects.create(
                user=user,
                activity_type='login',
                description='Daily login',
                points_earned=2
            )
    except Exception as e:
        logger.error(f"Error logging user login activity: {e}")