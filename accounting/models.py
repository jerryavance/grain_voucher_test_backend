# accounting/models.py - SIMPLIFIED FOR IMMEDIATE INVOICING
from django.db import models
from django.core.exceptions import ValidationError
from crm.models import Account
from authentication.models import GrainUser
from decimal import Decimal
from django.utils import timezone
import uuid

from hubs.models import Hub
from vouchers.models import GrainType


class Invoice(models.Model):
    """
    ✅ SIMPLIFIED: One invoice per GRN/delivery.
    Batching only happens when SENDING invoices to buyer.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('sent', 'Sent to Customer'),
        ('partially_paid', 'Partially Paid'),
        ('paid', 'Paid in Full'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=50, unique=True, editable=False)
    
    # Relationships - One invoice per GRN
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='invoices')
    grn = models.OneToOneField(
        'trade.GoodsReceivedNote',
        on_delete=models.PROTECT,
        related_name='invoice',
        help_text="One invoice per GRN"
    )
    trade = models.ForeignKey(
        'trade.Trade',
        on_delete=models.PROTECT,
        related_name='invoices',
        help_text="Trade can have multiple invoices (one per GRN)"
    )
    
    # Invoice Details
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    delivery_date = models.DateField(help_text="Date goods were delivered")
    
    # Line Item Details (from GRN)
    description = models.TextField()
    grain_type = models.CharField(max_length=100)
    quality_grade = models.CharField(max_length=100, blank=True)
    supplier_name = models.CharField(max_length=200)
    quantity_kg = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Amounts
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # ✅ NEW: BENNU fees only charged to buyer if applicable
    bennu_fees = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="BENNU fees (only if buyer pays)"
    )
    logistics_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    weighbridge_cost = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    other_charges = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    amount_paid = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    amount_due = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid')
    
    # Bank Instructions
    beneficiary_bank = models.CharField(max_length=200, blank=True)
    beneficiary_name = models.CharField(max_length=200, blank=True)
    beneficiary_account = models.CharField(max_length=100, blank=True)
    beneficiary_branch = models.CharField(max_length=200, blank=True)
    
    # Payment Terms
    payment_terms = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    
    # ✅ NEW: Batch sending tracking
    batch_sent_date = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When this invoice was sent as part of a batch to buyer"
    )
    batch_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="Batch identifier if sent with other invoices"
    )
    
    # Tracking
    created_by = models.ForeignKey(
        GrainUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='created_invoices'
    )
    last_reminder_sent = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issue_date', '-created_at']
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['account', 'status']),
            models.Index(fields=['due_date', 'payment_status']),
            models.Index(fields=['grn']),
            models.Index(fields=['trade']),
            models.Index(fields=['batch_id']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.account.name} - GRN {self.grn.grn_number}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        
        # Calculate amounts
        self.calculate_amounts()
        
        # Update payment status
        self.update_payment_status()
        
        super().save(*args, **kwargs)

    def generate_invoice_number(self):
        """Generate unique invoice number"""
        date_str = timezone.now().strftime('%Y%m%d')
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        count = Invoice.objects.filter(created_at__gte=today_start).count() + 1
        return f"INV-{date_str}-{count:04d}"

    def populate_from_grn(self):
        """Auto-populate fields from GRN"""
        if not self.grn:
            return
            
        trade = self.grn.trade
        self.trade = trade
        self.account = trade.buyer
        self.grain_type = trade.grain_type.name
        self.quality_grade = trade.quality_grade.name if trade.quality_grade else ''
        self.supplier_name = f"{trade.supplier.first_name} {trade.supplier.last_name}".strip()
        self.quantity_kg = self.grn.net_weight_kg
        self.unit_price = trade.selling_price
        self.delivery_date = self.grn.delivery_date
        
        # Calculate due date based on trade payment terms
        from datetime import timedelta
        self.due_date = self.delivery_date + timedelta(days=trade.payment_terms_days)
        
        # ✅ NEW: Only add BENNU fees if buyer pays
        if trade.bennu_fees_payer == 'buyer':
            self.bennu_fees = trade.bennu_fees
        elif trade.bennu_fees_payer == 'split':
            self.bennu_fees = trade.bennu_fees / Decimal('2')
        else:
            self.bennu_fees = Decimal('0.00')
        
        # Add other costs
        self.logistics_cost = trade.transport_cost_per_kg * self.quantity_kg
        self.weighbridge_cost = trade.weighbridge_cost
        
        self.description = (
            f"{self.grain_type} - {self.quality_grade} | "
            f"Supplier: {self.supplier_name} | "
            f"Delivered: {self.delivery_date} | "
            f"GRN: {self.grn.grn_number}"
        )
        
        self.payment_terms = f"Payment due within {trade.payment_terms_days} days - {trade.get_payment_terms_display()}"

    def calculate_amounts(self):
        """Calculate invoice amounts"""
        # Subtotal from quantity and unit price
        self.subtotal = self.quantity_kg * self.unit_price
        
        # Add additional charges
        add_on_charges = (
            self.bennu_fees + 
            self.logistics_cost + 
            self.weighbridge_cost + 
            self.other_charges
        )
        
        # Calculate tax
        self.tax_amount = (self.subtotal * self.tax_rate) / Decimal('100')
        
        # Calculate total
        self.total_amount = self.subtotal + add_on_charges + self.tax_amount - self.discount_amount
        
        # Calculate amount due
        self.amount_due = self.total_amount - self.amount_paid

    def update_payment_status(self):
        """Update payment status based on amounts"""
        if self.amount_paid == 0:
            self.payment_status = 'unpaid'
        elif self.amount_paid >= self.total_amount:
            self.payment_status = 'paid'
            self.status = 'paid'
        else:
            self.payment_status = 'partial'
            self.status = 'partially_paid'
        
        # Check if overdue
        if self.payment_status != 'paid' and self.due_date < timezone.now().date():
            self.payment_status = 'overdue'
            if self.status not in ['cancelled', 'paid']:
                self.status = 'overdue'

    def days_overdue(self):
        """Calculate days overdue"""
        if self.payment_status == 'paid':
            return 0
        today = timezone.now().date()
        if today > self.due_date:
            return (today - self.due_date).days
        return 0

    def get_total_add_on_charges(self):
        """Get total of all add-on charges"""
        return self.bennu_fees + self.logistics_cost + self.weighbridge_cost + self.other_charges


class Payment(models.Model):
    """Payment records linked to invoices"""
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_money', 'Mobile Money'),
        ('cheque', 'Cheque'),
        ('credit_card', 'Credit Card'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_number = models.CharField(max_length=50, unique=True, editable=False)
    
    # Relationships
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, editable=False)
    
    # Payment Details
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    
    # Payment Reference
    reference_number = models.CharField(max_length=100, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    
    # Notes
    notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    
    # Reconciliation
    reconciled = models.BooleanField(default=False)
    reconciled_date = models.DateTimeField(null=True, blank=True)
    reconciled_by = models.ForeignKey(
        GrainUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reconciled_payments'
    )
    
    # Tracking
    created_by = models.ForeignKey(
        GrainUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='recorded_payments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['invoice', 'status']),
            models.Index(fields=['payment_date']),
        ]

    def __str__(self):
        return f"Payment {self.payment_number} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.payment_number:
            self.payment_number = self.generate_payment_number()
        
        if not self.account_id:
            self.account = self.invoice.account
        
        super().save(*args, **kwargs)

    def generate_payment_number(self):
        """Generate unique payment number"""
        date_str = timezone.now().strftime('%Y%m%d')
        count = Payment.objects.filter(created_at__date=timezone.now().date()).count() + 1
        return f"PAY-{date_str}-{count:04d}"


class InvoiceBatch(models.Model):
    """
    ✅ NEW: Track batches of invoices sent together to buyers
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch_number = models.CharField(max_length=50, unique=True, editable=False)
    
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='invoice_batches')
    
    # Batch details
    batch_date = models.DateTimeField(default=timezone.now)
    period_start = models.DateField()
    period_end = models.DateField()
    
    invoice_count = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # Email/sending tracking
    sent_via_email = models.BooleanField(default=False)
    email_sent_date = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    
    created_by = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-batch_date']
        indexes = [
            models.Index(fields=['account', 'batch_date']),
            models.Index(fields=['period_start', 'period_end']),
        ]

    def __str__(self):
        return f"Batch {self.batch_number} - {self.account.name} ({self.invoice_count} invoices)"

    def save(self, *args, **kwargs):
        if not self.batch_number:
            self.batch_number = self.generate_batch_number()
        super().save(*args, **kwargs)

    def generate_batch_number(self):
        """Generate unique batch number"""
        date_str = timezone.now().strftime('%Y%m%d')
        count = InvoiceBatch.objects.filter(created_at__date=timezone.now().date()).count() + 1
        return f"BATCH-{date_str}-{count:04d}"


# JournalEntry and Budget models remain similar...
class JournalEntry(models.Model):
    """
    General ledger journal entries for accounting.
    """
    ENTRY_TYPE_CHOICES = [
        ('sale', 'Sale'),
        ('payment', 'Payment Received'),
        ('purchase', 'Purchase/COGS'),
        ('expense', 'Expense'),
        ('adjustment', 'Adjustment'),
        ('commission', 'Commission Expense'),
        ('deposit', 'Farmer Deposit'),
        ('redemption', 'Voucher Redemption'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entry_number = models.CharField(max_length=50, unique=True, editable=False)
    
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPE_CHOICES, default='adjustment')
    entry_date = models.DateField(default=timezone.now)
    
    # Accounting entries
    description = models.CharField(max_length=255)
    debit_account = models.CharField(max_length=100)
    credit_account = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    # References
    related_trade = models.ForeignKey('trade.Trade', on_delete=models.SET_NULL, null=True, blank=True)
    related_invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_entries')
    related_payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_entries')
    
    notes = models.TextField(blank=True)
    
    # Tracking
    created_by = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Reversal
    is_reversed = models.BooleanField(default=False)
    reversed_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reverses'
    )

    class Meta:
        ordering = ['-entry_date', '-created_at']
        indexes = [
            models.Index(fields=['entry_date', 'entry_type']),
            models.Index(fields=['related_trade']),
            models.Index(fields=['related_invoice']),
        ]
        verbose_name_plural = 'Journal Entries'

    def __str__(self):
        return f"JE {self.entry_number} - {self.entry_type}"

    def save(self, *args, **kwargs):
        if not self.entry_number:
            self.entry_number = self.generate_entry_number()
        super().save(*args, **kwargs)

    def generate_entry_number(self):
        """Generate unique journal entry number"""
        date_str = timezone.now().strftime('%Y%m%d')
        count = JournalEntry.objects.filter(created_at__date=timezone.now().date()).count() + 1
        return f"JE-{date_str}-{count:04d}"


class Budget(models.Model):
    """Budget tracking by period, hub, and grain type"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    period = models.DateField()
    hub = models.ForeignKey(Hub, on_delete=models.PROTECT, null=True, blank=True)
    grain_type = models.ForeignKey(GrainType, on_delete=models.PROTECT, null=True, blank=True)
    budgeted_amount = models.DecimalField(max_digits=15, decimal_places=2)
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period']
        indexes = [
            models.Index(fields=['period', 'hub']),
            models.Index(fields=['period', 'grain_type']),
        ]

    def __str__(self):
        hub_str = self.hub.name if self.hub else 'All Hubs'
        grain_str = self.grain_type.name if self.grain_type else 'All Grains'
        return f"Budget {self.period} - {hub_str} - {grain_str}"

    def variance(self):
        return self.budgeted_amount - self.actual_amount

    def variance_percentage(self):
        if self.budgeted_amount > 0:
            return (self.variance() / self.budgeted_amount) * Decimal('100')
        return Decimal('0.00')

    def is_over_budget(self):
        return self.actual_amount > self.budgeted_amount