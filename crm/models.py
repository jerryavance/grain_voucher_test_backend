# crm/models.py
from django.db import models
from authentication.models import GrainUser
from hubs.models import Hub
from utils.constants import USER_ROLES  # Assuming extended with 'bdm', 'client'
import uuid

class Lead(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=17)
    email = models.EmailField(blank=True)
    source = models.CharField(max_length=50)  # e.g., 'referral', 'website'
    status = models.CharField(max_length=20, choices=[('new', 'New'), ('qualified', 'Qualified'), ('lost', 'Lost')], default='new')
    assigned_to = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, related_name='leads')  # BDM
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'assigned_to'])]
        ordering = ['-created_at']

    def __str__(self):
        return f"Lead: {self.name} ({self.status})"

class Account(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=[('customer', 'Customer'), ('supplier', 'Supplier'), ('investor', 'Investor')])
    credit_terms_days = models.PositiveIntegerField(default=30)  # For BNPL
    hub = models.ForeignKey(Hub, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=['type'])]
        ordering = ['name']

    def __str__(self):
        return f"Account: {self.name} ({self.type})"

class Contact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='contacts')
    user = models.OneToOneField(GrainUser, on_delete=models.SET_NULL, null=True, blank=True)  # Link to client user
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=17)
    email = models.EmailField(blank=True)
    role = models.CharField(max_length=50, blank=True)  # e.g., 'Buyer'
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"Contact: {self.name} for {self.account}"

class Opportunity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    expected_volume_mt = models.DecimalField(max_digits=12, decimal_places=2)
    expected_price_per_mt = models.DecimalField(max_digits=12, decimal_places=2)
    stage = models.CharField(max_length=20, choices=[('prospect', 'Prospect'), ('quote', 'Quote'), ('won', 'Won'), ('lost', 'Lost')], default='prospect')
    assigned_to = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True)  # BDM
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Opportunity: {self.name} ({self.stage})"

class Contract(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    opportunity = models.OneToOneField(Opportunity, on_delete=models.CASCADE)
    terms = models.TextField()
    signed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=[('draft', 'Draft'), ('signed', 'Signed'), ('executed', 'Executed')], default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Contract for {self.opportunity}"