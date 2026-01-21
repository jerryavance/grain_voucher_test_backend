# investors/models.py
from django.db import models
from django.utils import timezone
from authentication.models import GrainUser
from hubs.models import Hub
import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError


class InvestorAccount(models.Model):
    """
    Main account for an investor tracking their capital and returns.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investor = models.OneToOneField(GrainUser, on_delete=models.CASCADE, related_name='investor_account')
    
    # Balances
    total_deposited = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Total capital deposited")
    total_utilized = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Capital currently in trades/loans")
    available_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Available for allocation")
    
    # Earnings
    total_margin_earned = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Total profits earned")
    total_margin_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Profits withdrawn")
    total_interest_earned = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Interest from loans")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['investor']),
        ]

    def __str__(self):
        return f"Investor Account for {self.investor}"

    def update_balance(self, amount, is_deposit=True):
        """Update balance for deposits or withdrawals"""
        if is_deposit:
            self.total_deposited += amount
            self.available_balance += amount
        else:
            if self.available_balance < amount:
                raise ValidationError("Insufficient balance")
            self.available_balance -= amount
        self.save()

    def allocate_to_trade(self, amount):
        """Allocate capital to a trade"""
        if amount > self.available_balance:
            raise ValidationError("Insufficient available balance")
        self.available_balance -= amount
        self.total_utilized += amount
        self.save()

    def release_from_trade(self, amount, profit=Decimal('0.00')):
        """Release capital from completed trade with profit"""
        self.total_utilized -= amount
        self.available_balance += (amount + profit)
        self.total_margin_earned += profit
        self.save()

    def get_total_value(self):
        """Get total account value (available + utilized + earnings)"""
        return self.available_balance + self.total_utilized + self.total_margin_earned - self.total_margin_paid


class InvestorDeposit(models.Model):
    """Records investor deposits into their account"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investor_account = models.ForeignKey(InvestorAccount, on_delete=models.CASCADE, related_name='deposits')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    deposit_date = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-deposit_date']

    def __str__(self):
        return f"Deposit {self.id} of {self.amount} by {self.investor_account.investor}"


class InvestorWithdrawal(models.Model):
    """Records investor withdrawal requests and approvals"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investor_account = models.ForeignKey(InvestorAccount, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    withdrawal_date = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='pending'
    )
    notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        GrainUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_withdrawals'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-withdrawal_date']
        indexes = [
            models.Index(fields=['investor_account', 'status']),
        ]

    def __str__(self):
        return f"Withdrawal {self.id} of {self.amount} by {self.investor_account.investor}"

    def approve(self, approved_by):
        if self.status != 'pending':
            raise ValidationError("Withdrawal is not in pending status")
        self.status = 'approved'
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.investor_account.update_balance(self.amount, is_deposit=False)
        self.save()

    def reject(self, notes=""):
        if self.status != 'pending':
            raise ValidationError("Withdrawal is not in pending status")
        self.status = 'rejected'
        self.notes = notes or "Withdrawal rejected"
        self.save()


class ProfitSharingAgreement(models.Model):
    """
    Defines profit sharing terms between investor and bennu.
    Different investors can have different agreements.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investor_account = models.ForeignKey(InvestorAccount, on_delete=models.CASCADE, related_name='profit_agreements')
    
    # Terms
    profit_threshold = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=2.00,
        help_text="Profit % threshold - below this investor gets 100%"
    )
    investor_share = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=75.00,
        help_text="Investor's share % above threshold"
    )
    bennu_share = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=25.00,
        help_text="bennu's share % above threshold"
    )
    
    # Metadata
    effective_date = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-effective_date']

    def __str__(self):
        return f"Profit Sharing for {self.investor_account.investor}"

    def clean(self):
        if self.investor_share + self.bennu_share != 100:
            raise ValidationError("Investor and bennu shares must sum to 100%")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)