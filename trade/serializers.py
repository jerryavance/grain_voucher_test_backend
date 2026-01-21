# trade/serializers.py - CORRECTED VERSION
from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum

from crm.models import Account
from vouchers.models import GrainType, QualityGrade
from vouchers.serializers import GrainTypeSerializer, QualityGradeSerializer, VoucherSerializer
from .models import Trade, TradeFinancing, TradeLoan, TradeCost, Brokerage, GoodsReceivedNote
from crm.serializers import AccountSerializer
from authentication.serializers import UserSerializer
from hubs.serializers import HubSerializer
from authentication.models import GrainUser
from hubs.models import Hub


class TradeCostSerializer(serializers.ModelSerializer):
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = TradeCost
        fields = ['id', 'trade', 'cost_type', 'description', 'amount', 'is_per_unit', 'total_amount', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_total_amount(self, obj):
        amount = float(obj.amount)
        if obj.is_per_unit and obj.trade:
            return amount * float(obj.trade.quantity_kg)
        return amount


class BrokerageSerializer(serializers.ModelSerializer):
    agent = UserSerializer(read_only=True)
    agent_id = serializers.PrimaryKeyRelatedField(
        queryset=GrainUser.objects.filter(role__in=['bdm', 'agent']),
        source='agent',
        write_only=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = Brokerage
        fields = ['id', 'trade', 'agent', 'agent_id', 'commission_type', 'commission_value', 'amount', 'notes', 'created_at']
        read_only_fields = ['id', 'amount', 'created_at']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['commission_value'] = float(instance.commission_value)
        representation['amount'] = float(instance.amount)
        return representation


class GoodsReceivedNoteSerializer(serializers.ModelSerializer):
    trade_number = serializers.CharField(source='trade.trade_number', read_only=True)
    grain_type = serializers.CharField(source='trade.grain_type.name', read_only=True)
    quality_grade = serializers.CharField(source='trade.quality_grade.name', read_only=True)

    class Meta:
        model = GoodsReceivedNote
        fields = '__all__'
        read_only_fields = ['id', 'grn_number', 'created_at', 'updated_at']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['gross_weight_kg'] = float(instance.gross_weight_kg) if instance.gross_weight_kg else None
        representation['tare_weight_kg'] = float(instance.tare_weight_kg) if instance.tare_weight_kg else None
        representation['net_weight_kg'] = float(instance.net_weight_kg) if instance.net_weight_kg else None
        return representation


class TradeFinancingSerializer(serializers.ModelSerializer):
    investor = UserSerializer(source='investor_account.investor', read_only=True)
    investor_account_id = serializers.UUIDField(write_only=True)
    trade_number = serializers.CharField(source='trade.trade_number', read_only=True)

    class Meta:
        model = TradeFinancing
        fields = [
            'id', 'trade', 'trade_number', 'investor', 'investor_account_id',
            'allocated_amount', 'allocation_percentage', 'margin_earned',
            'investor_margin', 'bennu_margin', 'allocation_date', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'allocation_percentage', 'margin_earned', 
            'investor_margin', 'bennu_margin', 'allocation_date',
            'created_at', 'updated_at'
        ]

    def validate_investor_account_id(self, value):
        from investors.models import InvestorAccount
        if not InvestorAccount.objects.filter(id=value).exists():
            raise serializers.ValidationError("Invalid investor account ID.")
        return value

    def create(self, validated_data):
        from investors.models import InvestorAccount
        investor_account_id = validated_data.pop('investor_account_id')
        investor_account = InvestorAccount.objects.get(id=investor_account_id)
        validated_data['investor_account'] = investor_account
        return super().create(validated_data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['allocated_amount'] = float(instance.allocated_amount)
        representation['allocation_percentage'] = float(instance.allocation_percentage)
        representation['margin_earned'] = float(instance.margin_earned)
        representation['investor_margin'] = float(instance.investor_margin)
        representation['bennu_margin'] = float(instance.bennu_margin)
        return representation


class TradeLoanSerializer(serializers.ModelSerializer):
    investor = UserSerializer(source='investor_account.investor', read_only=True)
    investor_account_id = serializers.UUIDField(write_only=True)
    trade_number = serializers.CharField(source='trade.trade_number', read_only=True)
    total_due = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()

    class Meta:
        model = TradeLoan
        fields = [
            'id', 'trade', 'trade_number', 'investor', 'investor_account_id',
            'amount', 'interest_rate', 'disbursement_date', 'due_date',
            'status', 'amount_repaid', 'interest_earned', 'total_due',
            'outstanding_balance', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'disbursement_date', 'interest_earned', 'created_at', 'updated_at']

    def get_total_due(self, obj):
        return float(obj.get_total_due())

    def get_outstanding_balance(self, obj):
        return float(obj.get_outstanding_balance())

    def create(self, validated_data):
        from investors.models import InvestorAccount
        investor_account_id = validated_data.pop('investor_account_id')
        investor_account = InvestorAccount.objects.get(id=investor_account_id)
        validated_data['investor_account'] = investor_account
        return super().create(validated_data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['amount'] = float(instance.amount)
        representation['interest_rate'] = float(instance.interest_rate)
        representation['amount_repaid'] = float(instance.amount_repaid)
        representation['interest_earned'] = float(instance.interest_earned)
        return representation


class TradeSerializer(serializers.ModelSerializer):
    """
    ✅ CLEAN VERSION - NO INVOICE ACCESS IN SERIALIZER
    Payment info will be calculated by separate endpoint if needed
    """
    
    # Related objects (read-only)
    buyer = AccountSerializer(read_only=True)
    supplier = UserSerializer(read_only=True)
    grain_type = GrainTypeSerializer(read_only=True)
    quality_grade = QualityGradeSerializer(read_only=True)
    hub = HubSerializer(read_only=True)
    initiated_by = UserSerializer(read_only=True)
    approved_by = UserSerializer(read_only=True)
    vouchers_detail = VoucherSerializer(source='vouchers', many=True, read_only=True)
    additional_costs = TradeCostSerializer(many=True, read_only=True)
    brokerages = BrokerageSerializer(many=True, read_only=True)
    financing_allocations = TradeFinancingSerializer(many=True, read_only=True)
    loans = TradeLoanSerializer(many=True, read_only=True)

    bennu_fees_payer_display = serializers.CharField(source='get_bennu_fees_payer_display', read_only=True)
    loss_summary = serializers.SerializerMethodField()
    
    # ✅ NEW: Delivery progress tracking
    delivery_completion_percentage = serializers.SerializerMethodField()
    delivered_quantity_kg = serializers.SerializerMethodField()
    remaining_quantity_kg = serializers.SerializerMethodField()
    
    # Write-only foreign keys
    buyer_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.filter(type='customer'),
        source='buyer',
        write_only=True
    )
    supplier_id = serializers.PrimaryKeyRelatedField(
        queryset=GrainUser.objects.filter(role='farmer'),
        source='supplier',
        write_only=True
    )
    grain_type_id = serializers.PrimaryKeyRelatedField(
        queryset=GrainType.objects.all(),
        source='grain_type',
        write_only=True
    )
    quality_grade_id = serializers.PrimaryKeyRelatedField(
        queryset=QualityGrade.objects.all(),
        source='quality_grade',
        write_only=True
    )
    hub_id = serializers.PrimaryKeyRelatedField(
        queryset=Hub.objects.all(),
        source='hub',
        write_only=True
    )

    # Calculated fields
    total_brokerage_cost = serializers.SerializerMethodField()
    total_additional_costs = serializers.SerializerMethodField()
    net_profit = serializers.SerializerMethodField()
    vouchers_count = serializers.SerializerMethodField()
    inventory_available = serializers.SerializerMethodField()
    total_financing_allocated = serializers.SerializerMethodField()
    total_loans = serializers.SerializerMethodField()
    grn_count = serializers.SerializerMethodField()
    
    # Status display
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    delivery_status_display = serializers.CharField(source='get_delivery_status_display', read_only=True)
    payment_terms_display = serializers.CharField(source='get_payment_terms_display', read_only=True)

    class Meta:
        model = Trade
        fields = [
            'id', 'trade_number',
            'buyer', 'buyer_id', 'supplier', 'supplier_id',
            'grain_type', 'grain_type_id', 'quality_grade', 'quality_grade_id',
            'hub', 'hub_id',
            'gross_tonnage', 'net_tonnage', 'quantity_kg', 'quantity_bags', 'bag_weight_kg',
            'buying_price', 'selling_price',
            'aflatoxin_qa_cost', 'weighbridge_cost', 'offloading_cost',
            'loading_cost', 'transport_cost_per_kg', 'financing_fee_percentage',
            'financing_days', 'git_insurance_percentage', 'deduction_percentage',
            'other_expenses', 'bennu_fees',
            'total_trade_cost', 'payable_by_buyer', 'margin',
            'gross_margin_percentage', 'roi_percentage',
            'total_brokerage_cost', 'total_additional_costs', 'net_profit',
            'payment_terms', 'payment_terms_display',
            'payment_terms_days', 'credit_terms_days',
            'delivery_status', 'delivery_status_display', 'delivery_date',
            'delivery_location', 'delivery_distance_km',
            'expected_delivery_date', 'actual_delivery_date',
            'vehicle_number', 'driver_name', 'driver_id', 'driver_phone',
            'gross_weight_kg', 'tare_weight_kg', 'net_weight_kg',
            'status', 'status_display', 'initiated_by', 'approved_by',
            'approved_at', 'allocation_complete',
            'requires_financing', 'financing_complete',
            'total_financing_allocated', 'total_loans',
            'financing_allocations', 'loans',
            'vouchers_count', 'vouchers_detail', 'inventory_available',
            'additional_costs', 'brokerages',
            'remarks', 'internal_notes', 'contract_notes',
            'created_at', 'updated_at', 'is_active',
            'bennu_fees_payer', 'bennu_fees_payer_display',
            'loss_quantity_kg', 'loss_cost', 'loss_reason', 'loss_summary',
            'requires_voucher_allocation',
            'grn_count', 'delivery_completion_percentage', 'delivered_quantity_kg', 'remaining_quantity_kg',
        ]

    def get_loss_summary(self, obj):
        if obj.loss_quantity_kg > 0:
            return {
                'has_loss': True,
                'quantity_kg': float(obj.loss_quantity_kg),
                'cost': float(obj.loss_cost),
                'percentage': float((obj.loss_quantity_kg / obj.quantity_kg) * 100) if obj.quantity_kg > 0 else 0,
                'reason': obj.loss_reason
            }
        return {'has_loss': False}

    def get_grn_count(self, obj):
        """Get count of GRNs (and thus invoices) for this trade"""
        return obj.grns.count()

    def get_delivery_completion_percentage(self, obj):
        """Calculate what % of order has been delivered"""
        progress = obj.get_delivery_progress()
        return float(progress['completion_percentage'])

    def get_delivered_quantity_kg(self, obj):
        """Get total quantity delivered so far"""
        progress = obj.get_delivery_progress()
        return float(progress['delivered_kg'])

    def get_remaining_quantity_kg(self, obj):
        """Get remaining quantity to be delivered"""
        progress = obj.get_delivery_progress()
        return float(progress['remaining_kg'])

    def get_total_brokerage_cost(self, obj):
        return float(sum(b.amount for b in obj.brokerages.all()))

    def get_total_additional_costs(self, obj):
        total = Decimal('0.00')
        for cost in obj.additional_costs.all():
            if cost.is_per_unit:
                total += cost.amount * obj.quantity_kg
            else:
                total += cost.amount
        return float(total)

    def get_net_profit(self, obj):
        total_brokerage = Decimal(str(self.get_total_brokerage_cost(obj)))
        total_additional = Decimal(str(self.get_total_additional_costs(obj)))
        margin = Decimal(str(obj.margin or 0))
        net_profit = margin - total_brokerage - total_additional
        return float(net_profit)

    def get_vouchers_count(self, obj):
        return obj.vouchers.count()

    def get_inventory_available(self, obj):
        return obj.check_inventory_availability()

    def get_total_financing_allocated(self, obj):
        return float(obj.get_allocated_financing())

    def get_total_loans(self, obj):
        return float(sum(loan.amount for loan in obj.loans.all()))

    def validate(self, data):
        user = self.context['request'].user
        hub = data.get('hub')
        
        if user.role in ['bdm', 'agent']:
            user_membership = user.hub_memberships.filter(hub=hub, status='active').first()
            if not user_membership:
                raise serializers.ValidationError({"hub_id": "You do not have permission to create trades for this hub"})
        
        selling_price = data.get('selling_price')
        buying_price = data.get('buying_price')
        
        if selling_price and buying_price and selling_price <= buying_price:
            raise serializers.ValidationError({"selling_price": "Selling price must be greater than buying price"})
        
        return data

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['initiated_by'] = user
        validated_data['status'] = 'draft'
        
        trade = super().create(validated_data)
        return trade

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        decimal_fields = [
            'gross_tonnage', 'net_tonnage', 'quantity_kg', 'bag_weight_kg',
            'buying_price', 'selling_price', 'aflatoxin_qa_cost', 'weighbridge_cost',
            'offloading_cost', 'loading_cost', 'transport_cost_per_kg',
            'financing_fee_percentage', 'git_insurance_percentage', 'deduction_percentage',
            'other_expenses', 'bennu_fees', 'total_trade_cost', 'payable_by_buyer',
            'margin', 'gross_margin_percentage', 'roi_percentage',
            'delivery_distance_km', 'gross_weight_kg', 'tare_weight_kg',
            'net_weight_kg', 'loss_quantity_kg', 'loss_cost'
        ]
        for field in decimal_fields:
            if field in representation and representation[field] is not None:
                representation[field] = float(representation[field])
        
        integer_fields = ['quantity_bags', 'financing_days', 'payment_terms_days', 'credit_terms_days']
        for field in integer_fields:
            if field in representation and representation[field] is not None:
                representation[field] = int(representation[field])

        return representation


class TradeListSerializer(serializers.ModelSerializer):
    """Simplified list serializer"""
    buyer_name = serializers.CharField(source='buyer.name', read_only=True)
    supplier_name = serializers.SerializerMethodField()
    grain_type_name = serializers.CharField(source='grain_type.name', read_only=True)
    quality_grade_name = serializers.CharField(source='quality_grade.name', read_only=True)
    hub_name = serializers.CharField(source='hub.name', read_only=True)
    initiated_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    vouchers_count = serializers.IntegerField(source='vouchers.count', read_only=True)
    has_losses = serializers.SerializerMethodField()
    grn_count = serializers.SerializerMethodField()
    delivery_completion_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = [
            'id', 'trade_number',
            'buyer_name', 'supplier_name', 'grain_type_name',
            'quality_grade_name', 'hub_name',
            'net_tonnage', 'quantity_kg',
            'buying_price', 'selling_price', 'payable_by_buyer', 'margin',
            'roi_percentage', 'status', 'status_display',
            'delivery_status', 'initiated_by_name', 'vouchers_count',
            'allocation_complete', 'requires_financing', 'financing_complete',
            'delivery_date', 'created_at',
            'bennu_fees_payer', 'has_losses', 'grn_count', 'delivery_completion_percentage',
        ]

    def get_supplier_name(self, obj):
        if obj.supplier:
            return f"{obj.supplier.first_name} {obj.supplier.last_name}".strip() or obj.supplier.username
        return "Unknown Supplier"

    def get_initiated_by_name(self, obj):
        if obj.initiated_by:
            return f"{obj.initiated_by.first_name} {obj.initiated_by.last_name}".strip() or obj.initiated_by.username
        return "Unknown User"

    def get_has_losses(self, obj):
        return obj.loss_quantity_kg > 0

    def get_grn_count(self, obj):
        return obj.grns.count()

    def get_delivery_completion_percentage(self, obj):
        progress = obj.get_delivery_progress()
        return float(progress['completion_percentage'])


class VoucherAllocationSerializer(serializers.Serializer):
    allocation_type = serializers.ChoiceField(choices=['auto', 'manual'])
    voucher_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_null=True
    )

    def validate(self, data):
        if data.get('allocation_type') == 'manual' and not data.get('voucher_ids'):
            raise serializers.ValidationError({"voucher_ids": "This field is required for manual allocation."})
        return data


class TradeStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Trade.STATUS_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True)
    actual_delivery_date = serializers.DateField(required=False, allow_null=True)
    vehicle_number = serializers.CharField(required=False, allow_blank=True, max_length=50)
    driver_name = serializers.CharField(required=False, allow_blank=True, max_length=100)