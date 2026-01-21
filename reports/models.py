# reports/models.py
from django.db import models
from authentication.models import GrainUser
from hubs.models import Hub
import uuid
from django.utils import timezone


class ReportExport(models.Model):
    """Track generated report exports for download"""
    REPORT_TYPE_CHOICES = [
        ('supplier', 'Supplier Report'),
        ('trade', 'Trade Report'),
        ('invoice', 'Invoice Report'),
        ('payment', 'Payment Report'),
        ('depositor', 'Depositor Report'),
        ('voucher', 'Voucher Report'),
        ('inventory', 'Inventory Report'),
        ('investor', 'Investor Report'),
    ]
    
    FORMAT_CHOICES = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default='pdf')
    
    # Filters used
    filters = models.JSONField(default=dict, blank=True)
    
    # File info
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.IntegerField(null=True, blank=True, help_text="File size in bytes")
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    
    # Metadata
    generated_by = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, related_name='generated_reports')
    hub = models.ForeignKey(Hub, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Timestamps
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(help_text="Report download link expires after 7 days")
    
    # Stats
    record_count = models.IntegerField(default=0, help_text="Number of records in report")
    
    class Meta:
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['report_type', 'status']),
            models.Index(fields=['generated_by', 'requested_at']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.get_report_type_display()} - {self.status}"
    
    def save(self, *args, **kwargs):
        # Set expiry to 7 days from now if not set
        if not self.expires_at:
            from datetime import timedelta
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)
    
    def is_expired(self):
        """Check if download link has expired"""
        return timezone.now() > self.expires_at
    
    def mark_completed(self, file_path, record_count):
        """Mark report as completed"""
        self.status = 'completed'
        self.file_path = file_path
        self.record_count = record_count
        self.completed_at = timezone.now()
        self.save()
    
    def mark_failed(self, error_message):
        """Mark report as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save()


class ReportSchedule(models.Model):
    """Schedule recurring report generation"""
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    report_type = models.CharField(max_length=20, choices=ReportExport.REPORT_TYPE_CHOICES)
    format = models.CharField(max_length=10, choices=ReportExport.FORMAT_CHOICES, default='pdf')
    
    # Schedule settings
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    day_of_week = models.IntegerField(null=True, blank=True, help_text="0=Monday, 6=Sunday (for weekly)")
    day_of_month = models.IntegerField(null=True, blank=True, help_text="1-31 (for monthly)")
    time_of_day = models.TimeField(default='09:00:00')
    
    # Filters
    filters = models.JSONField(default=dict, blank=True)
    
    # Recipients
    recipients = models.ManyToManyField(GrainUser, related_name='scheduled_reports')
    
    # Settings
    is_active = models.BooleanField(default=True)
    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, related_name='created_schedules')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.get_frequency_display()}"