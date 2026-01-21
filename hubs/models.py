# hubs/models.py
from django.db import models
from django.urls import reverse
from django.conf import settings
from django.utils.text import slugify
from django.contrib.auth import get_user_model
import uuid

from authentication.backends import User
from authentication.models import GrainUser

class Hub(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, editable=False)
    location = models.CharField(max_length=255, blank=True)

    is_active = models.BooleanField(default=True, help_text="Designates whether this hub should be treated as active.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:  # auto-generate slug
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Hub.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('hubs:hub-detail', kwargs={'pk': self.pk})


class HubMembership(models.Model):
    """Represents a user's membership in a hub"""
    MEMBERSHIP_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('rejected', 'Rejected'),
    ]
    
    MEMBERSHIP_ROLE_CHOICES = [
        ('farmer', 'Farmer'),
        ('agent', 'Agent'),
        ('hub_admin', 'Hub Admin'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(GrainUser, on_delete=models.CASCADE, related_name='hub_memberships')
    # user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hub_memberships')
    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=MEMBERSHIP_ROLE_CHOICES, default='farmer')
    status = models.CharField(max_length=20, choices=MEMBERSHIP_STATUS_CHOICES, default='pending')
    
    # Request details
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_memberships'
    )
    
    # Additional info
    reason = models.TextField(blank=True, help_text="Why user wants to join this hub")
    notes = models.TextField(blank=True, help_text="Admin notes")
    
    class Meta:
        unique_together = ['user', 'hub']  # User can only have one membership per hub
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['hub', 'status']),
            models.Index(fields=['status']),
        ]
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.user.phone_number} - {self.hub.name} ({self.status})"
