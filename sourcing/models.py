# sourcing/models.py
from django.db import models
from django.utils import timezone
from authentication.models import GrainUser
from hubs.models import Hub
from vouchers.models import GrainType, QualityGrade
import uuid
from decimal import Decimal
from datetime import date, timedelta


def generate_order_number():
    """Generate unique source order number"""
    return f"SO-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"


def generate_supplier_invoice_number():
    """Generate unique supplier invoice number"""
    return f"SI-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"


def generate_payment_number():
    """Generate unique payment reference number"""
    return f"PAY-{timezone.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"


class SupplierProfile(models.Model):
    """Extended profile for suppliers/farmers who sell grain to Bennu"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(GrainUser, on_delete=models.CASCADE, related_name='supplier_profile')
    hub = models.ForeignKey(Hub, on_delete=models.SET_NULL, null=True, blank=True,
                             help_text="Primary hub/collection point for this supplier")
    
    # Business details
    business_name = models.CharField(max_length=255, blank=True)
    farm_location = models.TextField(blank=True)
    typical_grain_types = models.ManyToManyField(GrainType, blank=True, related_name='suppliers')
    
    # Status
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_suppliers')
    verified_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['hub', 'is_verified']),
        ]

    def __str__(self):
        return f"{self.business_name or self.user.get_full_name()} - {self.user.phone_number}"


class PaymentPreference(models.Model):
    """Payment methods a supplier has registered for receiving payments"""
    METHOD_CHOICES = [
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash Pickup'),
        ('check', 'Bank Check'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(SupplierProfile, on_delete=models.CASCADE, related_name='payment_preferences')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    
    # Method-specific details stored as JSON for flexibility
    # e.g. {"account_number":"...", "bank_name":"..."} for bank
    # e.g. {"phone":"..."} for mobile money
    details = models.JSONField(default=dict)
    
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['supplier', 'is_default']),
        ]

    def __str__(self):
        return f"{self.get_method_display()} for {self.supplier}"

    def save(self, *args, **kwargs):
        # Ensure only one default per supplier
        if self.is_default:
            PaymentPreference.objects.filter(
                supplier=self.supplier,
                is_default=True
            ).exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)


class SourceOrder(models.Model):
    """Bennu's order to purchase grain from a supplier"""
    STATUS_CHOICES = [
        ('draft',       'Draft'),            # Created by BDM/admin, not yet sent
        ('open',        'Open'),             # Sent to supplier, awaiting response
        ('accepted',    'Accepted'),         # Supplier has accepted
        ('in_transit',  'In Transit'),       # Grain is being shipped
        ('delivered',   'Delivered'),        # Received at hub, pending weighing/QC
        ('completed',   'Completed'),        # Weighed, QC passed, invoice generated
        ('cancelled',   'Cancelled'),        # Cancelled at any point
        ('rejected',    'Rejected'),         # Supplier rejected the offer
    ]

    LOGISTICS_CHOICES = [
        ('bennu_truck',      'Bennu Truck'),
        ('supplier_driver',  'Supplier Driver'),
        ('third_party',      'Third Party Logistics'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=50, unique=True, default=generate_order_number, editable=False)
    
    # Parties
    supplier = models.ForeignKey(SupplierProfile, on_delete=models.PROTECT, related_name='source_orders')
    hub = models.ForeignKey(Hub, on_delete=models.PROTECT,
                             help_text="Destination hub/warehouse")
    created_by = models.ForeignKey(GrainUser, on_delete=models.PROTECT, related_name='created_source_orders')

    # Grain details
    grain_type = models.ForeignKey(GrainType, on_delete=models.PROTECT)
    quantity_kg = models.DecimalField(max_digits=12, decimal_places=2)
    offered_price_per_kg = models.DecimalField(max_digits=10, decimal_places=2,
                                               help_text="Price we offer to buy at per kg")
    
    # Costs tracked on the order
    grain_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                      help_text="quantity_kg * offered_price_per_kg")
    weighbridge_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    logistics_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    handling_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_costs = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                      help_text="Sum of all costs — used for margin calculation later")
    
    # Payment
    payment_method = models.ForeignKey(PaymentPreference, on_delete=models.SET_NULL,
                                        null=True, blank=True,
                                        help_text="Supplier's chosen payment method for this order")
    
    # Logistics
    logistics_type = models.CharField(max_length=20, choices=LOGISTICS_CHOICES, blank=True)
    driver_name = models.CharField(max_length=255, blank=True)
    driver_phone = models.CharField(max_length=17, blank=True)
    
    # Expected delivery
    expected_delivery_date = models.DateField(null=True, blank=True)
    
    # Status & dates
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True, help_text="When order was sent to supplier")
    accepted_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['supplier', 'status']),
            models.Index(fields=['hub', 'status', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['order_number']),
        ]

    def __str__(self):
        return f"{self.order_number} - {self.supplier} ({self.get_status_display()})"

    def calculate_total_cost(self):
        """Recalculate and save total cost"""
        self.grain_cost = self.quantity_kg * self.offered_price_per_kg
        self.total_cost = (
            self.grain_cost + 
            self.weighbridge_cost +
            self.logistics_cost + 
            self.handling_cost + 
            self.other_costs
        )
        self.save(update_fields=['grain_cost', 'total_cost'])
        return self.total_cost

    def send_to_supplier(self):
        """Mark order as sent to supplier"""
        if self.status == 'draft':
            self.status = 'open'
            self.sent_at = timezone.now()
            self.save(update_fields=['status', 'sent_at'])
            return True
        return False

    def accept_order(self):
        """Supplier accepts the order"""
        if self.status == 'open':
            self.status = 'accepted'
            self.accepted_at = timezone.now()
            self.save(update_fields=['status', 'accepted_at'])
            return True
        return False

    def reject_order(self):
        """Supplier rejects the order"""
        if self.status == 'open':
            self.status = 'rejected'
            self.save(update_fields=['status'])
            return True
        return False

    def mark_in_transit(self):
        """Mark order as shipped/in transit"""
        if self.status == 'accepted':
            self.status = 'in_transit'
            self.shipped_at = timezone.now()
            self.save(update_fields=['status', 'shipped_at'])
            return True
        return False

    def mark_delivered(self):
        """Mark order as delivered to hub"""
        if self.status == 'in_transit':
            self.status = 'delivered'
            self.delivered_at = timezone.now()
            self.save(update_fields=['status', 'delivered_at'])
            return True
        return False


class SupplierInvoice(models.Model):
    """Invoice auto-generated for paying a supplier. One per SourceOrder."""
    STATUS_CHOICES = [
        ('draft',     'Draft'),          # Created but not yet payable
        ('pending',   'Pending Payment'),# Order accepted — payment is due
        ('partial',   'Partially Paid'), # Some amount paid
        ('paid',      'Paid'),           # Fully paid
        ('cancelled', 'Cancelled'),      # Order was cancelled
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=50, unique=True, default=generate_supplier_invoice_number, editable=False)
    source_order = models.OneToOneField(SourceOrder, on_delete=models.CASCADE, related_name='supplier_invoice')
    supplier = models.ForeignKey(SupplierProfile, on_delete=models.PROTECT, related_name='invoices')

    # Amounts
    amount_due = models.DecimalField(max_digits=14, decimal_places=2,
                                      help_text="Total amount owed to supplier (= grain_cost from order)")
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Payment details
    payment_method = models.ForeignKey(PaymentPreference, on_delete=models.SET_NULL, null=True, blank=True)
    payment_reference = models.CharField(max_length=255, blank=True,
                                          help_text="Bank/mobile money transaction reference")

    # Dates
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    issued_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issued_at']
        indexes = [
            models.Index(fields=['supplier', 'status']),
            models.Index(fields=['status', 'issued_at']),
            models.Index(fields=['invoice_number']),
        ]

    def __str__(self):
        return f"{self.invoice_number} - {self.supplier} ({self.get_status_display()})"

    def update_payment_status(self):
        """Update status based on payment amounts"""
        if self.amount_paid >= self.amount_due:
            self.status = 'paid'
            if not self.paid_at:
                self.paid_at = timezone.now()
        elif self.amount_paid > 0:
            self.status = 'partial'
        elif self.status != 'cancelled':
            self.status = 'pending'
        
        self.balance_due = self.amount_due - self.amount_paid
        self.save(update_fields=['status', 'balance_due', 'paid_at'])


class DeliveryRecord(models.Model):
    """Records the arrival of grain at a hub"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_order = models.OneToOneField(SourceOrder, on_delete=models.CASCADE, related_name='delivery')
    hub = models.ForeignKey(Hub, on_delete=models.PROTECT)
    
    received_by = models.ForeignKey(GrainUser, on_delete=models.PROTECT, related_name='received_deliveries')
    received_at = models.DateTimeField(default=timezone.now)
    
    # Driver/vehicle info at delivery
    driver_name = models.CharField(max_length=255, blank=True)
    vehicle_number = models.CharField(max_length=50, blank=True)
    
    # Initial observations
    apparent_condition = models.CharField(
        max_length=20,
        choices=[('good', 'Good'), ('fair', 'Fair'), ('poor', 'Poor')],
        default='good'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['source_order']),
            models.Index(fields=['hub', 'received_at']),
        ]

    def __str__(self):
        return f"Delivery for {self.source_order.order_number}"


class WeighbridgeRecord(models.Model):
    """Official weighing and quality check at the hub"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_order = models.OneToOneField(SourceOrder, on_delete=models.CASCADE, related_name='weighbridge')
    delivery = models.OneToOneField(DeliveryRecord, on_delete=models.CASCADE, related_name='weighbridge')
    
    weighed_by = models.ForeignKey(GrainUser, on_delete=models.PROTECT, related_name='weighbridge_records')
    weighed_at = models.DateTimeField(default=timezone.now)
    
    # Measurements
    gross_weight_kg = models.DecimalField(max_digits=12, decimal_places=2)
    tare_weight_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_weight_kg = models.DecimalField(max_digits=12, decimal_places=2,
                                         help_text="gross - tare. This is the billable/inventory weight.")
    moisture_level = models.DecimalField(max_digits=5, decimal_places=2)
    quality_grade = models.ForeignKey(QualityGrade, on_delete=models.PROTECT)
    
    # Did final weight differ from ordered quantity?
    quantity_variance_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0,
        help_text="net_weight_kg - source_order.quantity_kg (positive = over-delivered)")
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-weighed_at']
        indexes = [
            models.Index(fields=['source_order']),
            models.Index(fields=['weighed_at']),
        ]

    def __str__(self):
        return f"Weighbridge for {self.source_order.order_number}"

    def save(self, *args, **kwargs):
        # Calculate net weight and variance
        self.net_weight_kg = self.gross_weight_kg - self.tare_weight_kg
        self.quantity_variance_kg = self.net_weight_kg - self.source_order.quantity_kg
        super().save(*args, **kwargs)


class SupplierPayment(models.Model):
    """Payment record for supplier invoice"""
    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('processing', 'Processing'),
        ('completed',  'Completed'),
        ('failed',     'Failed'),
        ('refunded',   'Refunded'),
    ]
    
    METHOD_CHOICES = [
        ('mobile_money',   'Mobile Money'),
        ('bank_transfer',  'Bank Transfer'),
        ('cash',           'Cash'),
        ('check',          'Bank Check'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_number = models.CharField(max_length=50, unique=True, default=generate_payment_number, editable=False)
    
    # Linked documents
    supplier_invoice = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name='payments')
    source_order = models.ForeignKey(SourceOrder, on_delete=models.PROTECT, related_name='payments')
    
    # Payment details
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference_number = models.CharField(max_length=255, blank=True,
        help_text="Bank/mobile money transaction reference — this IS the payment proof")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    processed_by = models.ForeignKey(GrainUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_supplier_payments')
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['supplier_invoice', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['payment_number']),
        ]

    def __str__(self):
        return f"{self.payment_number} - {self.amount} ({self.get_status_display()})"


class Notification(models.Model):
    """Push/in-app notifications for suppliers and investors"""
    TYPE_CHOICES = [
        ('source_order_created',    'New Source Order'),
        ('source_order_status',     'Order Status Update'),
        ('invoice_generated',       'Invoice Generated'),
        ('payment_made',            'Payment Made'),
        ('payment_proof',           'Payment Proof Available'),
        ('trade_financed',          'Your Capital Allocated to Trade'),
        ('trade_completed',         'Trade Completed — Returns Available'),
        ('capital_returned',        'Capital & Margin Returned'),
        ('delivery_received',       'Delivery Received'),
        ('weighbridge_completed',   'Weighbridge Record Created'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(GrainUser, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Link to the relevant object (polymorphic via content type or separate FKs)
    related_object_type = models.CharField(max_length=50, blank=True)  # e.g. 'source_order'
    related_object_id = models.UUIDField(null=True, blank=True)
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', 'created_at']),
            models.Index(fields=['user', 'notification_type']),
        ]

    def __str__(self):
        return f"{self.title} - {self.user}"

    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.save(update_fields=['is_read'])