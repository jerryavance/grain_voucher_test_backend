# accounting/serializers.py - UPDATED FOR SIMPLIFIED INVOICING
from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone

from crm.models import Account
from trade.models import Trade, GoodsReceivedNote
from .models import Budget, Invoice, JournalEntry, Payment, InvoiceBatch
from crm.serializers import AccountSerializer
from authentication.serializers import UserSerializer


class InvoiceSerializer(serializers.ModelSerializer):
    """Simplified serializer for one invoice per GRN"""
    account = AccountSerializer(read_only=True)
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        source='account',
        write_only=True,
        required=False
    )
    
    created_by = UserSerializer(read_only=True)
    
    # GRN details
    grn_number = serializers.CharField(source='grn.grn_number', read_only=True)
    trade_number = serializers.CharField(source='trade.trade_number', read_only=True)
    
    # Calculated fields
    days_overdue = serializers.SerializerMethodField()
    total_add_on_charges = serializers.SerializerMethodField()
    
    # Display fields
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'account', 'account_id',
            'grn', 'grn_number', 'trade', 'trade_number',
            
            # Dates
            'issue_date', 'due_date', 'delivery_date',
            
            # Line item details (from GRN)
            'description', 'grain_type', 'quality_grade', 'supplier_name',
            'quantity_kg', 'unit_price',
            
            # Amounts
            'subtotal', 'bennu_fees', 'logistics_cost', 'weighbridge_cost',
            'other_charges', 'total_add_on_charges', 'tax_rate', 'tax_amount',
            'discount_amount', 'total_amount', 'amount_paid', 'amount_due',
            
            # Status
            'status', 'status_display', 'payment_status', 'payment_status_display',
            
            # Bank details
            'beneficiary_bank', 'beneficiary_name', 'beneficiary_account', 'beneficiary_branch',
            
            # Terms and notes
            'payment_terms', 'notes', 'internal_notes',
            
            # Batch tracking
            'batch_sent_date', 'batch_id',
            
            # Tracking
            'created_by', 'last_reminder_sent',
            
            # Calculated
            'days_overdue',
            
            # Timestamps
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'invoice_number', 'grn', 'trade', 'description',
            'grain_type', 'quality_grade', 'supplier_name', 'quantity_kg',
            'unit_price', 'subtotal', 'tax_amount', 'total_amount',
            'amount_paid', 'amount_due', 'payment_status',
            'batch_sent_date', 'batch_id', 'created_at', 'updated_at'
        ]

    def get_days_overdue(self, obj):
        return obj.days_overdue()

    def get_total_add_on_charges(self, obj):
        return float(obj.get_total_add_on_charges())

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Convert Decimal fields to float
        decimal_fields = [
            'quantity_kg', 'unit_price', 'subtotal', 'bennu_fees', 
            'logistics_cost', 'weighbridge_cost', 'other_charges', 
            'tax_rate', 'tax_amount', 'discount_amount', 'total_amount', 
            'amount_paid', 'amount_due'
        ]
        for field in decimal_fields:
            if representation.get(field) is not None:
                representation[field] = float(representation[field])
        return representation


class InvoiceListSerializer(serializers.ModelSerializer):
    """Simplified serializer for listing invoices"""
    account_name = serializers.CharField(source='account.name', read_only=True)
    grn_number = serializers.CharField(source='grn.grn_number', read_only=True)
    trade_number = serializers.CharField(source='trade.trade_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    days_overdue = serializers.SerializerMethodField()
    is_batched = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'account_name', 'grn_number', 'trade_number',
            'issue_date', 'due_date', 'delivery_date',
            'grain_type', 'quantity_kg', 'total_amount', 'amount_paid', 'amount_due',
            'status', 'status_display', 'payment_status', 'payment_status_display',
            'days_overdue', 'batch_id', 'batch_sent_date', 'is_batched',
            'created_at'
        ]

    def get_days_overdue(self, obj):
        return obj.days_overdue()

    def get_is_batched(self, obj):
        return bool(obj.batch_id)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        for field in ['quantity_kg', 'total_amount', 'amount_paid', 'amount_due']:
            if representation.get(field) is not None:
                representation[field] = float(representation[field])
        return representation


class InvoiceBatchSerializer(serializers.ModelSerializer):
    """Serializer for invoice batches"""
    account = AccountSerializer(read_only=True)
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        source='account',
        write_only=True
    )
    created_by = UserSerializer(read_only=True)
    invoice_list = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceBatch
        fields = [
            'id', 'batch_number', 'account', 'account_id',
            'batch_date', 'period_start', 'period_end',
            'invoice_count', 'total_amount',
            'sent_via_email', 'email_sent_date',
            'notes', 'created_by', 'created_at',
            'invoice_list'
        ]
        read_only_fields = [
            'id', 'batch_number', 'batch_date', 'invoice_count',
            'total_amount', 'email_sent_date', 'created_by', 'created_at'
        ]

    def get_invoice_list(self, obj):
        """Get list of invoice numbers in this batch"""
        invoices = Invoice.objects.filter(batch_id=obj.batch_number).values_list(
            'invoice_number', flat=True
        )
        return list(invoices)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if representation.get('total_amount') is not None:
            representation['total_amount'] = float(representation['total_amount'])
        return representation


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for payments"""
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all())
    invoice_details = InvoiceSerializer(source='invoice', read_only=True)
    account = AccountSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    reconciled_by = UserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'payment_number', 'invoice', 'invoice_details', 'account',
            'amount', 'payment_date', 'payment_method', 'payment_method_display',
            'reference_number', 'transaction_id', 'status', 'status_display',
            'notes', 'internal_notes', 'reconciled', 'reconciled_date',
            'reconciled_by', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'payment_number', 'account', 'reconciled_date',
            'reconciled_by', 'created_by', 'created_at', 'updated_at'
        ]

    def validate(self, data):
        """Validate payment data"""
        invoice = data.get('invoice') or (self.instance.invoice if self.instance else None)
        amount = data.get('amount')
        
        if invoice and amount:
            if amount > invoice.amount_due:
                raise serializers.ValidationError({
                    "amount": f"Payment amount ({amount}) exceeds invoice amount due ({invoice.amount_due})"
                })
            if amount <= 0:
                raise serializers.ValidationError({
                    "amount": "Payment amount must be greater than zero"
                })
        
        return data

    def create(self, validated_data):
        """Create payment and set created_by and account"""
        validated_data['created_by'] = self.context['request'].user
        validated_data['account'] = validated_data['invoice'].account
        return super().create(validated_data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if representation.get('amount') is not None:
            representation['amount'] = float(representation['amount'])
        return representation



# Add these at the bottom of your existing serializers.py

class JournalEntrySerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    related_trade = serializers.StringRelatedField(read_only=True)
    related_invoice = serializers.StringRelatedField(read_only=True)
    related_payment = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            'id', 'entry_number', 'entry_type', 'entry_date',
            'debit_account', 'credit_account', 'amount', 'description',
            'notes', 'is_reversed', 'created_by', 'created_at',
            'related_trade', 'related_invoice', 'related_payment'
        ]
        read_only_fields = ['entry_number', 'created_at']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if ret.get('amount') is not None:
            ret['amount'] = float(ret['amount'])
        return ret


class BudgetSerializer(serializers.ModelSerializer):
    hub = serializers.StringRelatedField(read_only=True)
    grain_type = serializers.StringRelatedField(read_only=True)
    variance = serializers.SerializerMethodField()
    variance_percentage = serializers.SerializerMethodField()
    is_over_budget = serializers.BooleanField(read_only=True)

    class Meta:
        model = Budget
        fields = [
            'id', 'period', 'hub', 'grain_type',
            'budgeted_amount', 'actual_amount',
            'variance', 'variance_percentage', 'is_over_budget',
            'created_at', 'updated_at'
        ]

    def get_variance(self, obj):
        return float(obj.variance())

    def get_variance_percentage(self, obj):
        return float(obj.variance_percentage())