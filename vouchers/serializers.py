# vouchers/serializers.py
from decimal import Decimal
from time import timezone
from django.utils import timezone
from rest_framework import serializers
from authentication.models import GrainUser
from hubs.models import Hub, HubMembership
from vouchers.models import (
    GrainType, QualityGrade, PriceFeed, Deposit, Voucher, 
    Redemption, PurchaseOffer, Inventory, LedgerEntry
)
from authentication.serializers import UserSerializer
from hubs.serializers import HubSerializer
class QualityGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QualityGrade
        fields = '__all__'

class GrainTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GrainType
        fields = ['id', 'name', 'description']

class PriceFeedSerializer(serializers.ModelSerializer):
    hub = HubSerializer(read_only=True)
    grain_type = GrainTypeSerializer(read_only=True)
    hub_id = serializers.PrimaryKeyRelatedField(
        queryset=Hub.objects.all(),
        source='hub',
        allow_null=True,  # Explicitly allow null for global price feeds
        required=False,   # Make hub_id optional
        write_only=True
    )
    grain_type_id = serializers.PrimaryKeyRelatedField(
        queryset=GrainType.objects.all(),
        source='grain_type',
        required=True,
        write_only=True
    )

    class Meta:
        model = PriceFeed
        fields = [
            'id', 'hub', 'hub_id', 'grain_type', 'grain_type_id',
            'price_per_kg', 'effective_date', 'created_at', 'updated_at'
        ]

    def validate(self, data):
        """
        Validate that the hub_id and grain_type_id combination is unique for the effective_date.
        """
        hub = data.get('hub')
        grain_type = data.get('grain_type')
        effective_date = data.get('effective_date')

        # Check for existing price feed with the same hub, grain_type, and effective_date
        existing = PriceFeed.objects.filter(
            hub=hub,
            grain_type=grain_type,
            effective_date=effective_date
        ).exclude(id=self.instance.id if self.instance else None)

        if existing.exists():
            raise serializers.ValidationError({
                "non_field_errors": f"A price feed for {grain_type.name} at {hub.name if hub else 'Global'} on {effective_date} already exists."
            })

        return data

class DepositSerializer(serializers.ModelSerializer):
    farmer = UserSerializer(read_only=True)
    farmer_id = serializers.PrimaryKeyRelatedField(
        queryset=GrainUser.objects.none(),  # Will be set dynamically
        write_only=True,
        source='farmer'
    )
    hub = HubSerializer(read_only=True)
    hub_id = serializers.PrimaryKeyRelatedField(
        queryset=Hub.objects.none(),  # Will be set dynamically
        write_only=True,
        source='hub',
        required=True
    )
    agent = UserSerializer(read_only=True)
    grain_type = serializers.PrimaryKeyRelatedField(
        queryset=GrainType.objects.all(),
        write_only=True
    )
    grain_type_details = GrainTypeSerializer(source='grain_type', read_only=True)
    quality_grade = serializers.PrimaryKeyRelatedField(
        queryset=QualityGrade.objects.all(),
        write_only=True
    )
    quality_grade_details = QualityGradeSerializer(source='quality_grade', read_only=True)
    value = serializers.SerializerMethodField()

    class Meta:
        model = Deposit
        fields = [
            'id', 'farmer', 'farmer_id', 'hub', 'hub_id', 'agent',
            'grain_type', 'grain_type_details', 'quality_grade', 'quality_grade_details',
            'quantity_kg', 'moisture_level', 'deposit_date', 'validated', 
            'grn_number', 'notes', 'value'
        ]
        read_only_fields = ['id', 'deposit_date', 'validated', 'grn_number']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if hasattr(self.context.get('request', None), 'user'):
            user = self.context['request'].user
            
            if user.is_authenticated and hasattr(user, 'role'):
                if user.role in ['hub_admin', 'agent']:
                    # Get hubs where user is an active admin or agent
                    user_hubs = user.hub_memberships.filter(
                        role__in=['hub_admin', 'agent'],
                        status='active'
                    ).values_list('hub', flat=True)
                    
                    # Restrict hub selection to user's managed hubs
                    self.fields['hub_id'].queryset = Hub.objects.filter(id__in=user_hubs)
                    
                    # Restrict farmer selection to active farmers in those hubs
                    farmer_ids = HubMembership.objects.filter(
                        hub__in=user_hubs,
                        role='farmer',
                        status='active'
                    ).values_list('user', flat=True)
                    self.fields['farmer_id'].queryset = GrainUser.objects.filter(id__in=farmer_ids)
                elif user.role == 'super_admin':
                    # Super admins can select any farmer and any hub
                    self.fields['farmer_id'].queryset = GrainUser.objects.filter(role='farmer')
                    self.fields['hub_id'].queryset = Hub.objects.all()

    def validate(self, data):
        user = self.context['request'].user
        farmer = data.get('farmer')
        hub = data.get('hub')
        
        # Validate farmer is active member of selected hub
        if farmer and hub:
            farmer_membership = farmer.hub_memberships.filter(
                hub=hub,
                status='active'
            ).first()
            
            if not farmer_membership:
                raise serializers.ValidationError({
                    "farmer_id": f"Selected farmer is not an active member of {hub.name}"
                })
        
        # Validate user can create deposits for this hub
        if user.role in ['hub_admin', 'agent']:
            user_membership = user.hub_memberships.filter(
                hub=hub,
                role__in=['hub_admin', 'agent'],
                status='active'
            ).first()
            
            if not user_membership:
                raise serializers.ValidationError({
                    "hub_id": "You do not have permission to create deposits for this hub"
                })
        
        # Validate moisture level against quality grade
        if 'quality_grade' in data and 'moisture_level' in data:
            quality = data['quality_grade']
            moisture = data['moisture_level']
            if not (quality.min_moisture <= moisture <= quality.max_moisture):
                raise serializers.ValidationError({
                    "moisture_level": "Moisture level not in the selected quality grade range."
                })
        
        return data

    def create(self, validated_data):
        user = self.context['request'].user
        farmer = validated_data.get('farmer')
        hub = validated_data.get('hub')
        
        # Set agent if user is an agent
        if user.role == 'agent':
            validated_data['agent'] = user
            validated_data['validated'] = False
        else:
            validated_data['validated'] = True
            
        return super().create(validated_data)

    def get_value(self, obj):
        return obj.calculate_value()

# Updated serializers in vouchers/serializers.py

class VoucherSerializer(serializers.ModelSerializer):
    deposit = DepositSerializer(read_only=True)
    holder = UserSerializer(read_only=True)
    verified_by = UserSerializer(read_only=True)
    can_be_traded = serializers.SerializerMethodField()
    can_be_redeemed = serializers.SerializerMethodField()
    verification_status_display = serializers.CharField(source='get_verification_status_display', read_only=True)

    class Meta:
        model = Voucher
        fields = '__all__'
        read_only_fields = [
            'id', 'issue_date', 'current_value', 'status', 
            'verification_status', 'verified_by', 'verified_at'
        ]

    def get_can_be_traded(self, obj):
        return obj.can_be_traded()
    
    def get_can_be_redeemed(self, obj):
        return obj.can_be_redeemed()

class RedemptionSerializer(serializers.ModelSerializer):
    voucher = serializers.PrimaryKeyRelatedField(
        queryset=Voucher.objects.none(),  # Will be set dynamically
        write_only=True
    )
    voucher_details = VoucherSerializer(source='voucher', read_only=True)
    requester = UserSerializer(read_only=True)

    class Meta:
        model = Redemption
        fields = [
            'id', 'voucher', 'voucher_details', 'requester', 'request_date',
            'amount', 'fee', 'net_payout', 'status', 'payment_method', 'notes'
        ]
        read_only_fields = ['id', 'request_date', 'fee', 'net_payout', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.context.get('request', None), 'user'):
            user = self.context['request'].user
            if user.is_authenticated and not getattr(self, 'swagger_fake_view', False):
                # Only allow redemption of verified vouchers held by the user
                self.fields['voucher'].queryset = Voucher.objects.filter(
                    holder=user,
                    verification_status='verified',
                    status__in=['issued', 'transferred']
                )

    def validate_voucher(self, value):
        """Additional validation to ensure voucher can be redeemed"""
        if not value.can_be_redeemed():
            raise serializers.ValidationError(
                "This voucher cannot be redeemed. It may be pending verification or already redeemed."
            )
        return value

    def create(self, validated_data):
        validated_data['requester'] = self.context['request'].user
        return super().create(validated_data)

class PurchaseOfferSerializer(serializers.ModelSerializer):
    investor = UserSerializer(read_only=True)
    voucher = serializers.PrimaryKeyRelatedField(
        queryset=Voucher.objects.none(),  # Will be set dynamically
        write_only=True
    )
    voucher_details = VoucherSerializer(source='voucher', read_only=True)

    class Meta:
        model = PurchaseOffer
        fields = [
            'id', 'investor', 'voucher', 'voucher_details', 
            'offer_price', 'offer_date', 'status', 'notes'
        ]
        read_only_fields = ['id', 'offer_date', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.context.get('request', None), 'user'):
            user = self.context['request'].user
            if user.is_authenticated and not getattr(self, 'swagger_fake_view', False):
                # Only allow offers on verified vouchers not held by investors
                self.fields['voucher'].queryset = Voucher.objects.filter(
                    status='issued',
                    verification_status='verified'
                ).exclude(holder__role='investor')

    def validate_voucher(self, value):
        """Additional validation to ensure voucher can be traded"""
        if not value.can_be_traded():
            raise serializers.ValidationError(
                "This voucher cannot be traded. It may be pending verification or not available for trading."
            )
        return value

    def create(self, validated_data):
        validated_data['investor'] = self.context['request'].user
        return super().create(validated_data)

class LedgerEntrySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    hub = HubSerializer(read_only=True)

    class Meta:
        model = LedgerEntry
        fields = '__all__'
        read_only_fields = [
            'id',
            'event_type',
            'related_object_id',
            'user',
            'hub',
            'timestamp',
            'description',
            'amount'
        ]


class InventorySerializer(serializers.ModelSerializer):
    hub = HubSerializer(read_only=True)
    hub_id = serializers.PrimaryKeyRelatedField(
        queryset=Hub.objects.none(),  # Will be set dynamically
        write_only=True,
        source='hub',
        required=False
    )
    grain_type = GrainTypeSerializer(read_only=True)
    grain_type_id = serializers.PrimaryKeyRelatedField(
        queryset=GrainType.objects.all(),
        write_only=True,
        source='grain_type',
        required=False
    )
    
    # Calculated fields
    utilization_percentage = serializers.SerializerMethodField()
    current_value_estimate = serializers.SerializerMethodField()
    reserved_quantity_kg = serializers.SerializerMethodField()
    
    # Additional info fields
    pending_deposits_count = serializers.SerializerMethodField()
    active_vouchers_count = serializers.SerializerMethodField()

    class Meta:
        model = Inventory
        fields = [
            'id', 'hub', 'hub_id', 'grain_type', 'grain_type_id',
            'total_quantity_kg', 'available_quantity_kg', 'reserved_quantity_kg',
            'utilization_percentage', 'current_value_estimate',
            'pending_deposits_count', 'active_vouchers_count',
            'last_updated'
        ]
        read_only_fields = ['id', 'last_updated']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set dynamic querysets based on user permissions
        if hasattr(self.context.get('request', None), 'user'):
            user = self.context['request'].user
            
            if user.is_authenticated and hasattr(user, 'role'):
                if user.role in ['hub_admin', 'agent']:
                    # Restrict to user's hubs
                    user_hubs = user.hub_memberships.filter(
                        role__in=['hub_admin', 'agent'],
                        status='active'
                    ).values_list('hub', flat=True)
                    self.fields['hub_id'].queryset = Hub.objects.filter(id__in=user_hubs)
                elif user.role == 'super_admin':
                    # Super admins can access all hubs
                    self.fields['hub_id'].queryset = Hub.objects.all()

    def get_utilization_percentage(self, obj):
        """Calculate percentage of total inventory that's been utilized"""
        if obj.total_quantity_kg > 0:
            utilized = obj.total_quantity_kg - obj.available_quantity_kg
            return round((utilized / obj.total_quantity_kg) * 100, 2)
        return 0.0

    def get_reserved_quantity_kg(self, obj):
        """Calculate reserved quantity (total - available)"""
        return obj.total_quantity_kg - obj.available_quantity_kg

    def get_current_value_estimate(self, obj):
        """Estimate current value based on latest price feed"""
        current_date = timezone.now().date()
        try:
            # First, try hub-specific price
            latest_hub_price = PriceFeed.objects.filter(
                hub=obj.hub,
                grain_type=obj.grain_type,
                effective_date__lte=current_date
            ).order_by('-effective_date').first()
            
            if latest_hub_price:
                return obj.available_quantity_kg * latest_hub_price.price_per_kg
            
            # Fallback to global price (hub=None)
            latest_global_price = PriceFeed.objects.filter(
                hub__isnull=True,
                grain_type=obj.grain_type,
                effective_date__lte=current_date
            ).order_by('-effective_date').first()
            
            if latest_global_price:
                return obj.available_quantity_kg * latest_global_price.price_per_kg
            
            return Decimal('0.00')
        except Exception:
            return Decimal('0.00')

    def get_pending_deposits_count(self, obj):
        """Count pending deposits for this hub/grain type combination"""
        return Deposit.objects.filter(
            hub=obj.hub,
            grain_type=obj.grain_type,
            validated=False
        ).count()

    def get_active_vouchers_count(self, obj):
        """Count active vouchers for this inventory"""
        return Voucher.objects.filter(
            deposit__hub=obj.hub,
            deposit__grain_type=obj.grain_type,
            status__in=['issued', 'transferred'],
            verification_status='verified'
        ).count()

    def validate(self, data):
        """Validate inventory data"""
        hub = data.get('hub')
        grain_type = data.get('grain_type')
        
        # Check if user has permission to manage this hub's inventory
        user = self.context['request'].user
        if user.role in ['hub_admin', 'agent']:
            user_membership = user.hub_memberships.filter(
                hub=hub,
                role__in=['hub_admin', 'agent'],
                status='active'
            ).first()
            
            if not user_membership:
                raise serializers.ValidationError({
                    "hub_id": "You do not have permission to manage inventory for this hub"
                })
        
        # Validate quantity constraints
        total_qty = data.get('total_quantity_kg', 0)
        available_qty = data.get('available_quantity_kg', 0)
        
        if available_qty > total_qty:
            raise serializers.ValidationError({
                "available_quantity_kg": "Available quantity cannot exceed total quantity"
            })
        
        if total_qty < 0 or available_qty < 0:
            raise serializers.ValidationError(
                "Quantities cannot be negative"
            )
        
        return data

    def create(self, validated_data):
        """Create inventory record"""
        # Check for existing inventory record
        hub = validated_data.get('hub')
        grain_type = validated_data.get('grain_type')
        
        existing = Inventory.objects.filter(hub=hub, grain_type=grain_type).first()
        if existing:
            raise serializers.ValidationError(
                f"Inventory record already exists for {grain_type.name} at {hub.name}"
            )
        
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Update inventory with audit logging"""
        user = self.context['request'].user
        
        # Log significant changes
        old_total = instance.total_quantity_kg
        old_available = instance.available_quantity_kg
        
        updated_instance = super().update(instance, validated_data)
        
        new_total = updated_instance.total_quantity_kg
        new_available = updated_instance.available_quantity_kg
        
        # Create ledger entry for significant changes
        if old_total != new_total or old_available != new_available:
            description_parts = []
            if old_total != new_total:
                description_parts.append(f"Total: {old_total} → {new_total}kg")
            if old_available != new_available:
                description_parts.append(f"Available: {old_available} → {new_available}kg")
            
            LedgerEntry.objects.create(
                event_type='inventory_adjustment',
                related_object_id=updated_instance.id,
                user=user,
                hub=updated_instance.hub,
                description=f"Inventory adjustment - {', '.join(description_parts)}",
                amount=new_total - old_total if old_total != new_total else Decimal('0.00')
            )
        
        return updated_instance