# trade/models.py - COMPLETE CORRECTED VERSION
from django.db import models
from django.core.exceptions import ValidationError
from vouchers.models import Voucher, Inventory, GrainType, QualityGrade
from crm.models import Account
from authentication.models import GrainUser
from hubs.models import Hub
from decimal import Decimal
from django.utils import timezone
import uuid


class Trade(models.Model):
    """
    Trade transaction - can have MULTIPLE invoices (one per GRN/delivery)
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('pending_allocation', 'Pending Allocation'),  # ✅ ADDED
        ('ready_for_delivery', 'Ready for Delivery'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rejected', 'Rejected'),
    ]

    DELIVERY_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
    ]

    PAYMENT_TERMS_CHOICES = [
        ('cash_on_delivery', 'Cash on Delivery'),
        ('24_hours', '24 Hours'),
        ('7_days', '7 Days'),
        ('14_days', '14 Days'),
        ('30_days', '30 Days'),
        ('custom', 'Custom Terms'),
    ]

    BENNU_FEES_PAYER_CHOICES = [
        ('buyer', 'Buyer'),
        ('seller', 'Seller'),
        ('split', 'Split 50/50'),
    ]

    # Basic Information
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade_number = models.CharField(max_length=50, unique=True, editable=False)

    # Parties
    buyer = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='purchases')
    supplier = models.ForeignKey(GrainUser, on_delete=models.PROTECT, related_name='supplied_trades')
    hub = models.ForeignKey(Hub, on_delete=models.PROTECT)
    
    # Grain Details
    grain_type = models.ForeignKey(GrainType, on_delete=models.PROTECT)
    quality_grade = models.ForeignKey(QualityGrade, on_delete=models.PROTECT)
    
    # Quantity & Weight
    gross_tonnage = models.DecimalField(max_digits=12, decimal_places=2)
    net_tonnage = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_kg = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_bags = models.IntegerField(null=True, blank=True)
    bag_weight_kg = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('100.00'))
    
    # Pricing
    buying_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Costs Breakdown
    aflatoxin_qa_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    weighbridge_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    offloading_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    loading_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    transport_cost_per_kg = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0.00'))
    financing_fee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    financing_days = models.IntegerField(default=0)
    git_insurance_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.30'))
    deduction_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    other_expenses = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # BENNU Fees
    bennu_fees = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    bennu_fees_payer = models.CharField(max_length=10, choices=BENNU_FEES_PAYER_CHOICES, default='buyer')
    
    # Loss tracking
    loss_quantity_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    loss_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    loss_reason = models.TextField(blank=True)
    
    # Calculated Totals
    total_trade_cost = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.00'))
    payable_by_buyer = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.00'))
    margin = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0.00'))
    gross_margin_percentage = models.DecimalField(max_digits=6, decimal_places=2, editable=False, default=Decimal('0.00'))
    roi_percentage = models.DecimalField(max_digits=6, decimal_places=2, editable=False, default=Decimal('0.00'))
    
    # Payment Information
    payment_terms = models.CharField(max_length=30, choices=PAYMENT_TERMS_CHOICES, default='24_hours')
    payment_terms_days = models.IntegerField(default=1)
    credit_terms_days = models.IntegerField(default=0)
    
    # Delivery Information
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS_CHOICES, default='pending')
    delivery_date = models.DateField()
    delivery_location = models.TextField()
    delivery_distance_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    expected_delivery_date = models.DateField(null=True, blank=True)
    actual_delivery_date = models.DateField(null=True, blank=True)

    # Vehicle & Transport
    vehicle_number = models.CharField(max_length=50, blank=True, null=True)
    driver_name = models.CharField(max_length=100, blank=True, null=True)
    driver_id = models.CharField(max_length=50, blank=True, null=True)
    driver_phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Weight Details
    gross_weight_kg = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tare_weight_kg = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    net_weight_kg = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Status & Workflow
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    initiated_by = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, related_name='initiated_trades')
    approved_by = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_trades')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Voucher Allocation (Optional)
    vouchers = models.ManyToManyField(Voucher, related_name='trades', blank=True)
    allocation_complete = models.BooleanField(default=False)
    requires_voucher_allocation = models.BooleanField(default=False)
    
    # Investor Financing (Optional)
    requires_financing = models.BooleanField(default=False)
    financing_complete = models.BooleanField(default=False)
    
    # Notes
    remarks = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    contract_notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'hub']),
            models.Index(fields=['buyer', 'status']),
            models.Index(fields=['delivery_status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['trade_number']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Trade {self.trade_number} - {self.buyer.name}"

    def save(self, *args, **kwargs):
        if not self.trade_number:
            self.trade_number = self.generate_trade_number()
        
        # Calculate quantity_kg from net_tonnage
        self.quantity_kg = self.net_tonnage * Decimal('1000')
        
        # Calculate loss cost if there are losses
        if self.loss_quantity_kg > 0:
            self.loss_cost = self.loss_quantity_kg * self.buying_price
        
        # Calculate costs and margins
        self.calculate_costs()
        
        super().save(*args, **kwargs)

    def generate_trade_number(self):
        """Generate unique trade number"""
        date_str = timezone.now().strftime('%Y%m%d')
        return f"TRD-{date_str}-{str(uuid.uuid4())[:8].upper()}"

    def calculate_costs(self):
        """Calculate all cost components and profitability"""
        purchase_cost = self.buying_price * self.quantity_kg
        transport_total = self.transport_cost_per_kg * self.quantity_kg
        
        # Financing costs
        financing_cost = Decimal('0.00')
        if self.financing_days > 0 and self.financing_fee_percentage > 0:
            daily_rate = self.financing_fee_percentage / Decimal('100') / Decimal('365')
            financing_cost = purchase_cost * daily_rate * Decimal(str(self.financing_days))
        
        # GIT Insurance
        git_cost = (self.selling_price * self.quantity_kg) * (self.git_insurance_percentage / Decimal('100'))
        
        # Deductions
        deduction_cost = purchase_cost * (self.deduction_percentage / Decimal('100'))
        
        # BENNU fees based on who pays
        bennu_cost_to_trade = Decimal('0.00')
        bennu_cost_to_buyer = Decimal('0.00')
        
        if self.bennu_fees_payer == 'seller':
            bennu_cost_to_trade = self.bennu_fees
        elif self.bennu_fees_payer == 'buyer':
            bennu_cost_to_buyer = self.bennu_fees
        elif self.bennu_fees_payer == 'split':
            bennu_cost_to_trade = self.bennu_fees / Decimal('2')
            bennu_cost_to_buyer = self.bennu_fees / Decimal('2')
        
        # Total trade cost
        self.total_trade_cost = (
            purchase_cost +
            self.aflatoxin_qa_cost +
            self.weighbridge_cost +
            self.offloading_cost +
            self.loading_cost +
            transport_total +
            financing_cost +
            git_cost +
            deduction_cost +
            self.other_expenses +
            bennu_cost_to_trade +
            self.loss_cost
        )
        
        # Revenue & Margin
        self.payable_by_buyer = (self.selling_price * self.quantity_kg) + bennu_cost_to_buyer
        self.margin = self.payable_by_buyer - self.total_trade_cost
        
        # Percentages
        if self.payable_by_buyer > 0:
            self.gross_margin_percentage = (self.margin / self.payable_by_buyer) * Decimal('100')
        
        if self.total_trade_cost > 0:
            self.roi_percentage = (self.margin / self.total_trade_cost) * Decimal('100')

    def get_delivery_progress(self):
        """
        Calculate delivery progress for multi-delivery scenario.
        Returns dict with delivery stats.
        """
        from django.db.models import Sum
        
        delivered_so_far = self.grns.aggregate(
            total=Sum('net_weight_kg')
        )['total'] or Decimal('0.00')
        
        remaining = self.quantity_kg - delivered_so_far
        completion_pct = (delivered_so_far / self.quantity_kg * 100) if self.quantity_kg > 0 else Decimal('0')
        
        return {
            'total_ordered_kg': self.quantity_kg,
            'delivered_kg': delivered_so_far,
            'remaining_kg': remaining,
            'completion_percentage': completion_pct,
            'is_fully_delivered': remaining <= 0,
            'delivery_count': self.grns.count()
        }

    def can_create_delivery(self):
        """Check if more deliveries can be created"""
        progress = self.get_delivery_progress()
        return (
            progress['remaining_kg'] > 0 and 
            self.status in ['ready_for_delivery', 'in_transit', 'delivered']
        )

    def progress_to_next_status(self, user=None, notes=''):
        """Progress trade to next logical status"""
        transitions = {
            'draft': 'pending_approval',
            'pending_approval': 'approved',
            'approved': 'ready_for_delivery',  # Default if no financing/allocation needed
            'pending_allocation': 'ready_for_delivery',  # ✅ ADDED
            'ready_for_delivery': 'in_transit',
            'in_transit': 'delivered',
            'delivered': 'completed',
        }
        
        current_status = self.status
        next_status = transitions.get(current_status)
        
        if not next_status:
            raise ValidationError(f"Cannot progress from status '{current_status}'")
        
        # ✅ UPDATED: Check financing/allocation when leaving 'approved'
        if current_status == 'approved':
            # If requires financing and not complete, block progression
            if self.requires_financing and not self.financing_complete:
                raise ValidationError("Trade requires financing before it can proceed")
            
            # If requires voucher allocation, route to pending_allocation
            if self.requires_voucher_allocation and not self.allocation_complete:
                next_status = 'pending_allocation'
            
            # If requires financing and not complete, route to pending_allocation
            if self.requires_financing and not self.financing_complete:
                next_status = 'pending_allocation'
        
        # ✅ NEW: Validate when leaving pending_allocation
        if current_status == 'pending_allocation':
            if self.requires_voucher_allocation and not self.allocation_complete:
                raise ValidationError("Trade requires voucher allocation before it can proceed")
            if self.requires_financing and not self.financing_complete:
                raise ValidationError("Trade requires financing completion before it can proceed")
        
        # ✅ NEW: Block progression from 'delivered' to 'completed' without GRN
        if current_status == 'delivered' and next_status == 'completed':
            # Check if GRN exists
            if not self.grns.exists():
                raise ValidationError(
                    "Cannot complete trade without Goods Received Note (GRN). "
                    "Please create a GRN first using the 'create_delivery_batch' endpoint."
                )
            
            # Check if trade is fully delivered
            delivery_progress = self.get_delivery_progress()
            if not delivery_progress['is_fully_delivered']:
                remaining = delivery_progress['remaining_kg']
                raise ValidationError(
                    f"Cannot complete trade - {remaining} kg still pending delivery. "
                    f"Total ordered: {self.quantity_kg} kg, "
                    f"Delivered: {delivery_progress['delivered_kg']} kg"
                )
            
            # ✅ CRITICAL: Check if all invoices are paid
            try:
                from accounting.models import Invoice
                unpaid_invoices = Invoice.objects.filter(
                    trade=self,
                    payment_status__in=['unpaid', 'partial', 'overdue']
                )
                
                if unpaid_invoices.exists():
                    unpaid_count = unpaid_invoices.count()
                    total_due = sum(inv.amount_due for inv in unpaid_invoices)
                    raise ValidationError(
                        f"Cannot complete trade with {unpaid_count} unpaid invoice(s). "
                        f"Total outstanding: {total_due} UGX. "
                        "Please collect payments before marking trade as completed."
                    )
            except ImportError:
                # Invoice model not available - just check GRN exists
                pass
        
        # Update status
        old_status = self.status
        self.status = next_status
        
        # Add notes
        if notes:
            timestamp = timezone.now().strftime('%Y-%m-%d %H:%M')
            user_name = user.get_full_name() if user else 'System'
            self.internal_notes += f"\n[{timestamp}] Status: '{old_status}' → '{next_status}' by {user_name}: {notes}"
        
        # Handle specific transitions
        if next_status == 'approved' and user:
            self.approved_by = user
            self.approved_at = timezone.now()
        
        if next_status == 'in_transit':
            self.delivery_status = 'in_transit'
        
        if next_status == 'delivered':
            self.delivery_status = 'delivered'
            self.actual_delivery_date = timezone.now().date()
        
        self.save()
        return next_status

    def check_inventory_availability(self):
        """Check if sufficient inventory is available"""
        if not self.requires_voucher_allocation:
            return True
            
        try:
            inventory = Inventory.objects.get(hub=self.hub, grain_type=self.grain_type)
            return inventory.available_quantity_kg >= self.quantity_kg
        except Inventory.DoesNotExist:
            return False

    def get_total_financing_needed(self):
        """Calculate total financing needed"""
        return self.total_trade_cost

    def get_allocated_financing(self):
        """Get total financing allocated by investors"""
        return sum(alloc.allocated_amount for alloc in self.financing_allocations.all())

    def is_fully_financed(self):
        """Check if trade is fully financed"""
        if not self.requires_financing:
            return True
        return self.get_allocated_financing() >= self.get_total_financing_needed()


class TradeFinancing(models.Model):
    """Investor capital allocation to trades"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name='financing_allocations')
    investor_account = models.ForeignKey('investors.InvestorAccount', on_delete=models.CASCADE, related_name='trade_financings')
    
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2)
    allocation_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    
    # Profit Distribution
    margin_earned = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    investor_margin = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    bennu_margin = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    allocation_date = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['trade', 'investor_account']
        ordering = ['-allocation_date']

    def __str__(self):
        return f"Financing for Trade {self.trade.trade_number}"

    def save(self, *args, **kwargs):
        if self.trade.total_trade_cost > 0:
            self.allocation_percentage = (self.allocated_amount / self.trade.total_trade_cost) * Decimal('100')
        super().save(*args, **kwargs)


class TradeLoan(models.Model):
    """Investor loans to finance trades"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('repaid', 'Repaid'),
        ('defaulted', 'Defaulted')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name='loans')
    investor_account = models.ForeignKey('investors.InvestorAccount', on_delete=models.CASCADE, related_name='trade_loans')
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    disbursement_date = models.DateTimeField(default=timezone.now)
    due_date = models.DateField()
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    amount_repaid = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    interest_earned = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-disbursement_date']

    def __str__(self):
        return f"Loan for Trade {self.trade.trade_number}"

    def calculate_interest(self):
        """Calculate interest based on loan duration"""
        days = (timezone.now().date() - self.disbursement_date.date()).days
        daily_rate = self.interest_rate / Decimal('100') / Decimal('365')
        self.interest_earned = self.amount * daily_rate * Decimal(str(days))
        return self.interest_earned

    def get_total_due(self):
        """Get total amount due"""
        return self.amount + self.calculate_interest()

    def get_outstanding_balance(self):
        """Get remaining balance"""
        return self.get_total_due() - self.amount_repaid


class TradeCost(models.Model):
    """Additional flexible costs"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name='additional_costs')
    cost_type = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_per_unit = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.cost_type} - {self.trade.trade_number}"


class Brokerage(models.Model):
    """Commission/brokerage fees"""
    COMMISSION_TYPE_CHOICES = [
        ('percentage', 'Percentage of Trade Value'),
        ('per_mt', 'Per Metric Ton'),
        ('per_kg', 'Per Kilogram'),
        ('fixed', 'Fixed Amount'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name='brokerages')
    agent = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, related_name='brokerage_commissions')
    commission_type = models.CharField(max_length=20, choices=COMMISSION_TYPE_CHOICES, default='percentage')
    commission_value = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Brokerage for {self.trade.trade_number}"

    def save(self, *args, **kwargs):
        # Calculate brokerage amount
        if self.commission_type == 'percentage':
            self.amount = self.trade.payable_by_buyer * (self.commission_value / Decimal('100'))
        elif self.commission_type == 'per_mt':
            self.amount = self.trade.net_tonnage * self.commission_value
        elif self.commission_type == 'per_kg':
            self.amount = self.trade.quantity_kg * self.commission_value
        else:
            self.amount = self.commission_value
        super().save(*args, **kwargs)


class GoodsReceivedNote(models.Model):
    """Documents the receipt of goods - CREATES INVOICE AUTOMATICALLY"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grn_number = models.CharField(max_length=50, unique=True, editable=False)
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name='grns')
    
    # Loading Details
    point_of_loading = models.CharField(max_length=200)
    loading_date = models.DateField()
    
    # Delivery Details
    delivery_date = models.DateField()
    delivered_to_name = models.CharField(max_length=200)
    delivered_to_address = models.TextField()
    delivered_to_contact = models.CharField(max_length=50)
    
    # Vehicle & Driver
    vehicle_number = models.CharField(max_length=50)
    driver_name = models.CharField(max_length=100)
    driver_id_number = models.CharField(max_length=50)
    driver_phone = models.CharField(max_length=20)
    
    # Weight Details
    quantity_bags = models.IntegerField(null=True, blank=True)
    gross_weight_kg = models.DecimalField(max_digits=12, decimal_places=2)
    tare_weight_kg = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    net_weight_kg = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Signatures
    warehouse_manager_name = models.CharField(max_length=100)
    warehouse_manager_signature = models.TextField(blank=True)
    warehouse_manager_date = models.DateField()
    
    received_by_name = models.CharField(max_length=100)
    received_by_signature = models.TextField(blank=True)
    received_by_date = models.DateField()
    
    remarks = models.TextField(blank=True)
    reason = models.TextField(default="Goods receipt for purchase order into warehouse/stores")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"GRN {self.grn_number} - {self.trade.trade_number}"

    def save(self, *args, **kwargs):
        if not self.grn_number:
            self.grn_number = self.generate_grn_number()
        super().save(*args, **kwargs)

    def generate_grn_number(self):
        """Generate unique GRN number"""
        date_str = timezone.now().strftime('%Y%m%d')
        return f"GRN-{date_str}-{str(uuid.uuid4())[:8].upper()}"