# vouchers/models.py
from django.db import models
from django.utils import timezone
from authentication.models import GrainUser
from hubs.models import Hub
from utils.constants import USER_ROLES, GRAIN_TYPES, QUALITY_GRADES
import uuid
from decimal import Decimal
from django.utils import timezone
from datetime import date

class GrainType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class QualityGrade(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    min_moisture = models.DecimalField(max_digits=5, decimal_places=2)
    max_moisture = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class PriceFeed(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, null=True, blank=True)  # Hub-specific or global if null
    grain_type = models.ForeignKey(GrainType, on_delete=models.CASCADE)
    price_per_kg = models.DecimalField(max_digits=10, decimal_places=2)
    effective_date = models.DateField(default=date.today)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['hub', 'grain_type', 'effective_date']
        ordering = ['-effective_date']

    def __str__(self):
        return f"{self.grain_type} @ {self.price_per_kg} on {self.effective_date}"


def generate_grn_number():
    """Generate GRN using full UUID - most collision-resistant"""
    # return str(uuid.uuid4())[:50]
    return f"GRN-{str(uuid.uuid4())}"

class Deposit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # farmer = models.ForeignKey(GrainUser, on_delete=models.CASCADE, related_name='deposits')
    farmer = models.ForeignKey(GrainUser, on_delete=models.PROTECT, related_name='deposits')
    hub = models.ForeignKey(Hub, on_delete=models.CASCADE)
    agent = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='agent_deposits')
    grain_type = models.ForeignKey(GrainType, on_delete=models.PROTECT)
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=2)
    moisture_level = models.DecimalField(max_digits=5, decimal_places=2)
    quality_grade = models.ForeignKey(QualityGrade, on_delete=models.PROTECT)
    deposit_date = models.DateTimeField(default=timezone.now)
    validated = models.BooleanField(default=False)
    # grn_number = models.CharField(max_length=50, unique=True, blank=True)
    grn_number = models.CharField(max_length=50, unique=True, default=generate_grn_number, blank=True)
    # grn_number = models.CharField(max_length=100, unique=True, default=generate_full_uuid_grn, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['farmer', 'deposit_date']),
            models.Index(fields=['hub', 'deposit_date']),
        ]
        ordering = ['-deposit_date']

    def __str__(self):
        return f"Deposit {self.id} by {self.farmer} at {self.hub}"

    def calculate_value(self):
        current_date = timezone.now().date()
        
        # First, try hub-specific price
        latest_hub_price = PriceFeed.objects.filter(
            hub=self.hub,
            grain_type=self.grain_type,
            effective_date__lte=current_date
        ).order_by('-effective_date').first()
        
        if latest_hub_price:
            return self.quantity_kg * latest_hub_price.price_per_kg
        
        # Fallback to global price (hub=None)
        latest_global_price = PriceFeed.objects.filter(
            hub__isnull=True,
            grain_type=self.grain_type,
            effective_date__lte=current_date
        ).order_by('-effective_date').first()
        
        if latest_global_price:
            return self.quantity_kg * latest_global_price.price_per_kg
        
        return Decimal('0.00')

class Voucher(models.Model):
    STATUS_CHOICES = [
        ('pending_verification', 'Pending Verification'),  # New status for agent deposits
        ('issued', 'Issued'),
        ('transferred', 'Transferred'), 
        ('redeemed', 'Redeemed'),
        ('expired', 'Expired'),
    ]

    VERIFICATION_STATUS_CHOICES = [
        ('verified', 'Verified'),           # Hub admin deposit or approved agent deposit
        ('pending', 'Pending Verification'), # Agent deposit awaiting hub admin approval
        ('rejected', 'Rejected'),           # Hub admin rejected agent deposit
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    deposit = models.OneToOneField(Deposit, on_delete=models.CASCADE, related_name='voucher')
    holder = models.ForeignKey(GrainUser, on_delete=models.CASCADE, related_name='vouchers')
    issue_date = models.DateTimeField(default=timezone.now)
    entry_price = models.DecimalField(max_digits=10, decimal_places=2)
    current_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_STATUS_CHOICES, default='verified')
    verified_by = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_vouchers')
    verified_at = models.DateTimeField(null=True, blank=True)
    grn_number = models.CharField(max_length=50, blank=True)
    signature_farmer = models.TextField(blank=True)
    signature_agent = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['holder', 'status']),
            models.Index(fields=['deposit']),
            models.Index(fields=['verification_status']),
        ]
        ordering = ['-issue_date']

    def __str__(self):
        return f"Voucher {self.id} for {self.deposit.quantity_kg}kg - {self.verification_status}"

    def update_value(self):
        self.current_value = self.deposit.calculate_value()
        self.save()

    def can_be_traded(self):
        """Check if voucher can be traded/transferred"""
        return self.verification_status == 'verified' and self.status == 'issued'

    def can_be_redeemed(self):
        """Check if voucher can be redeemed"""
        return self.verification_status == 'verified' and self.status in ['issued', 'transferred']

class Redemption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='redemptions')
    requester = models.ForeignKey(GrainUser, on_delete=models.CASCADE)
    request_date = models.DateTimeField(default=timezone.now)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    net_payout = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('paid', 'Paid')], default='pending')
    #payment_method = models.CharField(max_length=50, choices=[('cash', 'Cash'), ('momo', 'Mobile Money'), ('bank', 'Bank Transfer'), ('grain', 'In-Kind Grain')])
    payment_method = models.CharField(max_length=50, choices=[('cash', 'Cash Pickup'), ('mobile_money', 'Mobile Money'), ('bank_transfer', 'Bank Transfer'), ('check', 'Bank Check'),('grain', 'In-Kind Grain')])
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-request_date']

    def __str__(self):
        return f"Redemption {self.id} for Voucher {self.voucher.id}"

    def calculate_fees_and_net(self):
        service_fee = self.voucher.current_value * Decimal('0.02')
        storage_days = (timezone.now() - self.voucher.issue_date).days
        storage_fee = Decimal(storage_days) * Decimal('0.01') * self.voucher.deposit.quantity_kg
        self.fee = service_fee + storage_fee
        self.net_payout = self.amount - self.fee
        self.save()

class PurchaseOffer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investor = models.ForeignKey(GrainUser, on_delete=models.CASCADE, related_name='offers')
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='offers')
    offer_price = models.DecimalField(max_digits=12, decimal_places=2)
    offer_date = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected')], default='pending')
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['investor', 'voucher']
        ordering = ['-offer_date']

    def __str__(self):
        return f"Offer {self.id} by {self.investor} for Voucher {self.voucher.id}"

class Inventory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hub = models.ForeignKey(Hub, on_delete=models.CASCADE)
    grain_type = models.ForeignKey(GrainType, on_delete=models.PROTECT)
    total_quantity_kg = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    available_quantity_kg = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['hub', 'grain_type']

    def __str__(self):
        return f"Inventory at {self.hub} for {self.grain_type}"

class LedgerEntry(models.Model):
    EVENT_TYPES = [
        ('deposit', 'Deposit'),
        ('voucher_issue', 'Voucher Issue'),
        ('voucher_transfer', 'Voucher Transfer'),
        ('redemption', 'Redemption'),
        ('purchase', 'Purchase'),
        ('fee', 'Fee'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    related_object_id = models.UUIDField()
    user = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True)
    hub = models.ForeignKey(Hub, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(default=timezone.now)
    description = models.TextField()
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['event_type', 'timestamp']),
            models.Index(fields=['user']),
            models.Index(fields=['hub']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        return f"Ledger {self.id} - {self.event_type}"