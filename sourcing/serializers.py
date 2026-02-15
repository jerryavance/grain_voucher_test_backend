# sourcing/serializers.py
from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

from authentication.models import GrainUser
from hubs.models import Hub

from .models import (
    SupplierProfile, PaymentPreference, SourceOrder, SupplierInvoice,
    DeliveryRecord, WeighbridgeRecord, SupplierPayment, Notification
)
from authentication.serializers import UserSerializer
from hubs.serializers import HubSerializer
from vouchers.models import GrainType, QualityGrade


class GrainTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GrainType
        fields = '__all__'
        ref_name = 'SourcingGrainType'


class QualityGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = QualityGrade
        fields = ['id', 'name', 'min_moisture', 'max_moisture', 'description']


class PaymentPreferenceSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source='get_method_display', read_only=True)

    class Meta:
        model = PaymentPreference
        fields = [
            'id', 'supplier', 'method', 'method_display', 'details',
            'is_default', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        method = data.get('method')
        details = data.get('details', {})

        if method == 'mobile_money' and not details.get('phone'):
            raise serializers.ValidationError({
                "details": "Mobile money requires 'phone' in details"
            })
        elif method == 'bank_transfer':
            required_fields = ['account_number', 'bank_name', 'account_name']
            missing = [f for f in required_fields if not details.get(f)]
            if missing:
                raise serializers.ValidationError({
                    "details": f"Bank transfer requires: {', '.join(missing)}"
                })

        return data


class SupplierProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=GrainUser.objects.all(),
        source='user',
        write_only=True,
        required=False,
        allow_null=False,
    )
    hub = HubSerializer(read_only=True)
    hub_id = serializers.PrimaryKeyRelatedField(
        queryset=Hub.objects.all(),
        source='hub',
        write_only=True,
        required=False,
        allow_null=True
    )
    typical_grain_types = GrainTypeSerializer(many=True, read_only=True)
    typical_grain_type_ids = serializers.PrimaryKeyRelatedField(
        queryset=GrainType.objects.all(),
        source='typical_grain_types',
        many=True,
        write_only=True,
        required=False
    )
    payment_preferences = PaymentPreferenceSerializer(many=True, read_only=True)
    verified_by = UserSerializer(read_only=True)

    total_orders = serializers.SerializerMethodField()
    total_supplied_kg = serializers.SerializerMethodField()

    class Meta:
        model = SupplierProfile
        fields = [
            'id', 'user', 'user_id', 'hub', 'hub_id',
            'business_name', 'farm_location',
            'typical_grain_types', 'typical_grain_type_ids',
            'is_verified', 'verified_by', 'verified_at',
            'payment_preferences', 'total_orders', 'total_supplied_kg',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'is_verified', 'verified_by', 'verified_at', 'created_at', 'updated_at']

    def validate(self, data):
        """
        FIX: Catch duplicate profiles at validation time so DRF returns a
        clean 400 instead of a DB IntegrityError 500.

        Two cases:
          1. user_id provided in payload → DRF maps it to data['user'] via
             source='user'. The old perform_create checked
             `'user' not in validated_data` which was always False here,
             silently skipping the guard and hitting the DB.
          2. user_id not provided (auto-assign) → fall back to request.user
             from serializer context.
        """
        if self.instance is None:
            user = data.get('user') or (
                self.context.get('request') and self.context['request'].user
            )
            if user and SupplierProfile.objects.filter(user=user).exists():
                raise serializers.ValidationError(
                    {"user_id": "A supplier profile already exists for this user."}
                )
        return data

    def get_total_orders(self, obj):
        return obj.source_orders.filter(status='completed').count()

    def get_total_supplied_kg(self, obj):
        from django.db.models import Sum
        total = obj.source_orders.filter(status='completed').aggregate(
            total=Sum('quantity_kg')
        )['total']
        return float(total) if total else 0.0


class SourceOrderListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.business_name', read_only=True)
    supplier_phone = serializers.CharField(source='supplier.user.phone_number', read_only=True)
    hub_name = serializers.CharField(source='hub.name', read_only=True)
    grain_type_name = serializers.CharField(source='grain_type.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = SourceOrder
        fields = [
            'id', 'order_number', 'supplier', 'supplier_name', 'supplier_phone',
            'hub', 'hub_name', 'grain_type', 'grain_type_name',
            'quantity_kg', 'offered_price_per_kg', 'total_cost',
            'status', 'status_display', 'created_by_name',
            'expected_delivery_date', 'created_at', 'accepted_at', 'delivered_at'
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        for field in ['quantity_kg', 'offered_price_per_kg', 'total_cost']:
            if representation.get(field) is not None:
                representation[field] = float(representation[field])
        return representation


class SourceOrderSerializer(serializers.ModelSerializer):
    supplier = SupplierProfileSerializer(read_only=True)
    supplier_id = serializers.PrimaryKeyRelatedField(
        queryset=SupplierProfile.objects.all(),
        source='supplier',
        write_only=True
    )
    hub = HubSerializer(read_only=True)
    hub_id = serializers.PrimaryKeyRelatedField(
        queryset=Hub.objects.all(),
        source='hub',
        write_only=True
    )
    grain_type = GrainTypeSerializer(read_only=True)
    grain_type_id = serializers.PrimaryKeyRelatedField(
        queryset=GrainType.objects.all(),
        source='grain_type',
        write_only=True
    )
    payment_method = PaymentPreferenceSerializer(read_only=True)
    payment_method_id = serializers.PrimaryKeyRelatedField(
        queryset=PaymentPreference.objects.all(),
        source='payment_method',
        write_only=True,
        required=False,
        allow_null=True
    )
    created_by = UserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    logistics_type_display = serializers.CharField(source='get_logistics_type_display', read_only=True)

    has_delivery = serializers.SerializerMethodField()
    has_weighbridge = serializers.SerializerMethodField()
    has_invoice = serializers.SerializerMethodField()

    class Meta:
        model = SourceOrder
        fields = [
            'id', 'order_number', 'supplier', 'supplier_id', 'hub', 'hub_id',
            'created_by', 'grain_type', 'grain_type_id',
            'quantity_kg', 'offered_price_per_kg',
            'grain_cost', 'weighbridge_cost', 'logistics_cost',
            'handling_cost', 'other_costs', 'total_cost',
            'payment_method', 'payment_method_id',
            'logistics_type', 'logistics_type_display',
            'driver_name', 'driver_phone', 'expected_delivery_date',
            'status', 'status_display',
            'created_at', 'sent_at', 'accepted_at', 'shipped_at',
            'delivered_at', 'completed_at', 'notes',
            'has_delivery', 'has_weighbridge', 'has_invoice'
        ]
        read_only_fields = [
            'id', 'order_number', 'created_by', 'grain_cost', 'total_cost',
            'created_at', 'sent_at', 'accepted_at', 'shipped_at',
            'delivered_at', 'completed_at'
        ]

    def get_has_delivery(self, obj):
        return hasattr(obj, 'delivery')

    def get_has_weighbridge(self, obj):
        return hasattr(obj, 'weighbridge')

    def get_has_invoice(self, obj):
        return hasattr(obj, 'supplier_invoice')

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        order = super().create(validated_data)
        order.calculate_total_cost()
        return order

    def update(self, instance, validated_data):
        order = super().update(instance, validated_data)
        cost_fields = ['quantity_kg', 'offered_price_per_kg', 'weighbridge_cost',
                       'logistics_cost', 'handling_cost', 'other_costs']
        if any(field in validated_data for field in cost_fields):
            order.calculate_total_cost()
        return order

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        decimal_fields = [
            'quantity_kg', 'offered_price_per_kg', 'grain_cost',
            'weighbridge_cost', 'logistics_cost', 'handling_cost',
            'other_costs', 'total_cost'
        ]
        for field in decimal_fields:
            if representation.get(field) is not None:
                representation[field] = float(representation[field])
        return representation


class DeliveryRecordSerializer(serializers.ModelSerializer):
    source_order = SourceOrderListSerializer(read_only=True)
    source_order_id = serializers.PrimaryKeyRelatedField(
        queryset=SourceOrder.objects.all(),
        source='source_order',
        write_only=True
    )
    hub = HubSerializer(read_only=True)
    hub_id = serializers.PrimaryKeyRelatedField(
        queryset=Hub.objects.all(),
        source='hub',
        write_only=True
    )
    received_by = UserSerializer(read_only=True)
    condition_display = serializers.CharField(source='get_apparent_condition_display', read_only=True)

    class Meta:
        model = DeliveryRecord
        fields = [
            'id', 'source_order', 'source_order_id', 'hub', 'hub_id',
            'received_by', 'received_at', 'driver_name', 'vehicle_number',
            'apparent_condition', 'condition_display', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'received_by', 'received_at', 'created_at']

    def create(self, validated_data):
        validated_data['received_by'] = self.context['request'].user

        with transaction.atomic():
            delivery = super().create(validated_data)
            delivery.source_order.mark_delivered()
            return delivery


class WeighbridgeRecordSerializer(serializers.ModelSerializer):
    source_order = SourceOrderListSerializer(read_only=True)
    source_order_id = serializers.PrimaryKeyRelatedField(
        queryset=SourceOrder.objects.all(),
        source='source_order',
        write_only=True
    )
    delivery = DeliveryRecordSerializer(read_only=True)
    delivery_id = serializers.PrimaryKeyRelatedField(
        queryset=DeliveryRecord.objects.all(),
        source='delivery',
        write_only=True
    )
    quality_grade = QualityGradeSerializer(read_only=True)
    quality_grade_id = serializers.PrimaryKeyRelatedField(
        queryset=QualityGrade.objects.all(),
        source='quality_grade',
        write_only=True
    )
    weighed_by = UserSerializer(read_only=True)

    class Meta:
        model = WeighbridgeRecord
        fields = [
            'id', 'source_order', 'source_order_id', 'delivery', 'delivery_id',
            'weighed_by', 'weighed_at',
            'gross_weight_kg', 'tare_weight_kg', 'net_weight_kg',
            'moisture_level', 'quality_grade', 'quality_grade_id',
            'quantity_variance_kg', 'notes', 'created_at'
        ]
        read_only_fields = [
            'id', 'weighed_by', 'weighed_at', 'net_weight_kg',
            'quantity_variance_kg', 'created_at'
        ]

    def create(self, validated_data):
        validated_data['weighed_by'] = self.context['request'].user

        with transaction.atomic():
            record = super().create(validated_data)

            source_order = record.source_order
            source_order.status = 'completed'
            source_order.completed_at = timezone.now()
            source_order.save(update_fields=['status', 'completed_at'])

            from vouchers.models import Inventory
            inventory, created = Inventory.objects.get_or_create(
                hub=source_order.hub,
                grain_type=source_order.grain_type,
                defaults={
                    'total_quantity_kg': Decimal('0.00'),
                    'available_quantity_kg': Decimal('0.00')
                }
            )
            inventory.total_quantity_kg += record.net_weight_kg
            inventory.available_quantity_kg += record.net_weight_kg
            inventory.save()

            return record

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        decimal_fields = [
            'gross_weight_kg', 'tare_weight_kg', 'net_weight_kg',
            'moisture_level', 'quantity_variance_kg'
        ]
        for field in decimal_fields:
            if representation.get(field) is not None:
                representation[field] = float(representation[field])
        return representation


class SupplierInvoiceSerializer(serializers.ModelSerializer):
    source_order = SourceOrderListSerializer(read_only=True)
    supplier = SupplierProfileSerializer(read_only=True)
    payment_method = PaymentPreferenceSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payments_list = serializers.SerializerMethodField()

    class Meta:
        model = SupplierInvoice
        fields = [
            'id', 'invoice_number', 'source_order', 'supplier',
            'amount_due', 'amount_paid', 'balance_due',
            'payment_method', 'payment_reference',
            'status', 'status_display',
            'issued_at', 'due_date', 'paid_at',
            'notes', 'payments_list',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'invoice_number', 'source_order', 'supplier',
            'amount_due', 'amount_paid', 'balance_due', 'status',
            'issued_at', 'paid_at', 'created_at', 'updated_at'
        ]

    def get_payments_list(self, obj):
        from .serializers import SupplierPaymentSerializer
        return SupplierPaymentSerializer(obj.payments.all(), many=True).data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        for field in ['amount_due', 'amount_paid', 'balance_due']:
            if representation.get(field) is not None:
                representation[field] = float(representation[field])
        return representation


class SupplierPaymentSerializer(serializers.ModelSerializer):
    supplier_invoice = serializers.PrimaryKeyRelatedField(
        queryset=SupplierInvoice.objects.all()
    )
    source_order = serializers.PrimaryKeyRelatedField(read_only=True)
    processed_by = UserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    method_display = serializers.CharField(source='get_method_display', read_only=True)

    class Meta:
        model = SupplierPayment
        fields = [
            'id', 'payment_number', 'supplier_invoice', 'source_order',
            'amount', 'method', 'method_display', 'reference_number',
            'status', 'status_display', 'processed_by',
            'created_at', 'completed_at', 'notes'
        ]
        read_only_fields = [
            'id', 'payment_number', 'source_order', 'processed_by',
            'created_at', 'completed_at'
        ]

    def create(self, validated_data):
        validated_data['processed_by'] = self.context['request'].user
        validated_data['source_order'] = validated_data['supplier_invoice'].source_order

        with transaction.atomic():
            payment = super().create(validated_data)

            if payment.status == 'completed':
                invoice = payment.supplier_invoice
                invoice.amount_paid += payment.amount
                invoice.update_payment_status()

                if not payment.completed_at:
                    payment.completed_at = timezone.now()
                    payment.save(update_fields=['completed_at'])

            return payment

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if representation.get('amount') is not None:
            representation['amount'] = float(representation['amount'])
        return representation


class NotificationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    type_display = serializers.CharField(source='get_notification_type_display', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'notification_type', 'type_display',
            'title', 'message', 'related_object_type', 'related_object_id',
            'is_read', 'created_at'
        ]
        read_only_fields = ['id', 'user', 'created_at']


class SupplierDashboardSerializer(serializers.Serializer):
    total_orders = serializers.IntegerField()
    pending_orders = serializers.IntegerField()
    completed_orders = serializers.IntegerField()
    total_supplied_kg = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_earned = serializers.DecimalField(max_digits=15, decimal_places=2)
    pending_payment = serializers.DecimalField(max_digits=15, decimal_places=2)
    recent_orders = SourceOrderListSerializer(many=True)
    recent_invoices = SupplierInvoiceSerializer(many=True)
    unread_notifications = serializers.IntegerField()









# # sourcing/serializers.py
# from rest_framework import serializers
# from decimal import Decimal
# from django.utils import timezone
# from django.db import transaction

# from authentication.models import GrainUser
# from hubs.models import Hub

# from .models import (
#     SupplierProfile, PaymentPreference, SourceOrder, SupplierInvoice,
#     DeliveryRecord, WeighbridgeRecord, SupplierPayment, Notification
# )
# from authentication.serializers import UserSerializer
# from hubs.serializers import HubSerializer
# from vouchers.models import GrainType, QualityGrade


# class GrainTypeSerializer(serializers.ModelSerializer):
#     """
#     GrainType serializer for sourcing app.
#     Fixed: Added unique ref_name to avoid conflict with vouchers app
#     """
#     class Meta:
#         model = GrainType
#         fields = '__all__'
#         ref_name = 'SourcingGrainType'


# class QualityGradeSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = QualityGrade
#         fields = ['id', 'name', 'min_moisture', 'max_moisture', 'description']


# class PaymentPreferenceSerializer(serializers.ModelSerializer):
#     method_display = serializers.CharField(source='get_method_display', read_only=True)

#     class Meta:
#         model = PaymentPreference
#         fields = [
#             'id', 'supplier', 'method', 'method_display', 'details',
#             'is_default', 'is_active', 'created_at', 'updated_at'
#         ]
#         read_only_fields = ['id', 'created_at', 'updated_at']

#     def validate(self, data):
#         """Validate payment preference details based on method"""
#         method = data.get('method')
#         details = data.get('details', {})

#         if method == 'mobile_money' and not details.get('phone'):
#             raise serializers.ValidationError({
#                 "details": "Mobile money requires 'phone' in details"
#             })
#         elif method == 'bank_transfer':
#             required_fields = ['account_number', 'bank_name', 'account_name']
#             missing = [f for f in required_fields if not details.get(f)]
#             if missing:
#                 raise serializers.ValidationError({
#                     "details": f"Bank transfer requires: {', '.join(missing)}"
#                 })

#         return data


# class SupplierProfileSerializer(serializers.ModelSerializer):
#     user = UserSerializer(read_only=True)
#     # user_id is optional — the view's perform_create injects request.user when
#     # it is not supplied (e.g. a farmer self-registering). Staff can still pass
#     # user_id explicitly to register a profile for another user.
#     user_id = serializers.PrimaryKeyRelatedField(
#         queryset=GrainUser.objects.all(),
#         source='user',
#         write_only=True,
#         required=False,
#         allow_null=False,
#     )
#     hub = HubSerializer(read_only=True)
#     hub_id = serializers.PrimaryKeyRelatedField(
#         queryset=Hub.objects.all(),
#         source='hub',
#         write_only=True,
#         required=False,
#         allow_null=True
#     )
#     typical_grain_types = GrainTypeSerializer(many=True, read_only=True)
#     typical_grain_type_ids = serializers.PrimaryKeyRelatedField(
#         queryset=GrainType.objects.all(),
#         source='typical_grain_types',
#         many=True,
#         write_only=True,
#         required=False
#     )
#     payment_preferences = PaymentPreferenceSerializer(many=True, read_only=True)
#     verified_by = UserSerializer(read_only=True)

#     # Stats
#     total_orders = serializers.SerializerMethodField()
#     total_supplied_kg = serializers.SerializerMethodField()

#     class Meta:
#         model = SupplierProfile
#         fields = [
#             'id', 'user', 'user_id', 'hub', 'hub_id',
#             'business_name', 'farm_location',
#             'typical_grain_types', 'typical_grain_type_ids',
#             'is_verified', 'verified_by', 'verified_at',
#             'payment_preferences', 'total_orders', 'total_supplied_kg',
#             'created_at', 'updated_at'
#         ]
#         read_only_fields = ['id', 'is_verified', 'verified_by', 'verified_at', 'created_at', 'updated_at']

#     def validate(self, data):
#         """
#         FIX: Catch duplicate profiles at validation time so DRF returns a
#         clean 400 JSON response instead of letting the database raise an
#         IntegrityError 500.

#         Two cases are handled:
#           1. user_id was provided in the payload → DRF maps it to data['user']
#              via source='user'. The original code checked
#              `'user' not in serializer.validated_data` in perform_create, which
#              was ALWAYS False when user_id was sent, so the duplicate check was
#              silently skipped and execution fell straight through to save().
#           2. user_id was NOT provided (auto-assign path) → data has no 'user'
#              key, so we fall back to request.user from serializer context.

#         Both cases are now resolved here before any DB write happens.
#         """
#         if self.instance is None:  # Only check on create, not update
#             # Case 1: explicit user_id in payload (stored as 'user' by DRF)
#             # Case 2: no user_id → fall back to the authenticated request user
#             user = data.get('user') or (
#                 self.context.get('request') and self.context['request'].user
#             )
#             if user and SupplierProfile.objects.filter(user=user).exists():
#                 raise serializers.ValidationError(
#                     {"user_id": "A supplier profile already exists for this user."}
#                 )
#         return data

#     def get_total_orders(self, obj):
#         return obj.source_orders.filter(status='completed').count()

#     def get_total_supplied_kg(self, obj):
#         from django.db.models import Sum
#         total = obj.source_orders.filter(status='completed').aggregate(
#             total=Sum('quantity_kg')
#         )['total']
#         return float(total) if total else 0.0


# class SourceOrderListSerializer(serializers.ModelSerializer):
#     """Lightweight serializer for listing orders"""
#     supplier_name = serializers.CharField(source='supplier.business_name', read_only=True)
#     supplier_phone = serializers.CharField(source='supplier.user.phone_number', read_only=True)
#     hub_name = serializers.CharField(source='hub.name', read_only=True)
#     grain_type_name = serializers.CharField(source='grain_type.name', read_only=True)
#     status_display = serializers.CharField(source='get_status_display', read_only=True)
#     created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

#     class Meta:
#         model = SourceOrder
#         fields = [
#             'id', 'order_number', 'supplier', 'supplier_name', 'supplier_phone',
#             'hub', 'hub_name', 'grain_type', 'grain_type_name',
#             'quantity_kg', 'offered_price_per_kg', 'total_cost',
#             'status', 'status_display', 'created_by_name',
#             'expected_delivery_date', 'created_at', 'accepted_at', 'delivered_at'
#         ]

#     def to_representation(self, instance):
#         representation = super().to_representation(instance)
#         # Convert Decimal to float
#         for field in ['quantity_kg', 'offered_price_per_kg', 'total_cost']:
#             if representation.get(field) is not None:
#                 representation[field] = float(representation[field])
#         return representation


# class SourceOrderSerializer(serializers.ModelSerializer):
#     """Full serializer for source order details"""
#     supplier = SupplierProfileSerializer(read_only=True)
#     supplier_id = serializers.PrimaryKeyRelatedField(
#         queryset=SupplierProfile.objects.all(),
#         source='supplier',
#         write_only=True
#     )
#     hub = HubSerializer(read_only=True)
#     hub_id = serializers.PrimaryKeyRelatedField(
#         queryset=Hub.objects.all(),
#         source='hub',
#         write_only=True
#     )
#     grain_type = GrainTypeSerializer(read_only=True)
#     grain_type_id = serializers.PrimaryKeyRelatedField(
#         queryset=GrainType.objects.all(),
#         source='grain_type',
#         write_only=True
#     )
#     payment_method = PaymentPreferenceSerializer(read_only=True)
#     payment_method_id = serializers.PrimaryKeyRelatedField(
#         queryset=PaymentPreference.objects.all(),
#         source='payment_method',
#         write_only=True,
#         required=False,
#         allow_null=True
#     )
#     created_by = UserSerializer(read_only=True)
#     status_display = serializers.CharField(source='get_status_display', read_only=True)
#     logistics_type_display = serializers.CharField(source='get_logistics_type_display', read_only=True)

#     # Related records
#     has_delivery = serializers.SerializerMethodField()
#     has_weighbridge = serializers.SerializerMethodField()
#     has_invoice = serializers.SerializerMethodField()

#     class Meta:
#         model = SourceOrder
#         fields = [
#             'id', 'order_number', 'supplier', 'supplier_id', 'hub', 'hub_id',
#             'created_by', 'grain_type', 'grain_type_id',
#             'quantity_kg', 'offered_price_per_kg',
#             'grain_cost', 'weighbridge_cost', 'logistics_cost',
#             'handling_cost', 'other_costs', 'total_cost',
#             'payment_method', 'payment_method_id',
#             'logistics_type', 'logistics_type_display',
#             'driver_name', 'driver_phone', 'expected_delivery_date',
#             'status', 'status_display',
#             'created_at', 'sent_at', 'accepted_at', 'shipped_at',
#             'delivered_at', 'completed_at', 'notes',
#             'has_delivery', 'has_weighbridge', 'has_invoice'
#         ]
#         read_only_fields = [
#             'id', 'order_number', 'created_by', 'grain_cost', 'total_cost',
#             'created_at', 'sent_at', 'accepted_at', 'shipped_at',
#             'delivered_at', 'completed_at'
#         ]

#     def get_has_delivery(self, obj):
#         return hasattr(obj, 'delivery')

#     def get_has_weighbridge(self, obj):
#         return hasattr(obj, 'weighbridge')

#     def get_has_invoice(self, obj):
#         return hasattr(obj, 'supplier_invoice')

#     def create(self, validated_data):
#         """Create source order with auto-calculated costs"""
#         validated_data['created_by'] = self.context['request'].user
#         order = super().create(validated_data)
#         order.calculate_total_cost()
#         return order

#     def update(self, instance, validated_data):
#         """Update and recalculate costs if relevant fields changed"""
#         order = super().update(instance, validated_data)

#         # Recalculate if any cost-related fields changed
#         cost_fields = ['quantity_kg', 'offered_price_per_kg', 'weighbridge_cost',
#                        'logistics_cost', 'handling_cost', 'other_costs']
#         if any(field in validated_data for field in cost_fields):
#             order.calculate_total_cost()

#         return order

#     def to_representation(self, instance):
#         representation = super().to_representation(instance)
#         # Convert Decimal fields to float
#         decimal_fields = [
#             'quantity_kg', 'offered_price_per_kg', 'grain_cost',
#             'weighbridge_cost', 'logistics_cost', 'handling_cost',
#             'other_costs', 'total_cost'
#         ]
#         for field in decimal_fields:
#             if representation.get(field) is not None:
#                 representation[field] = float(representation[field])
#         return representation


# class DeliveryRecordSerializer(serializers.ModelSerializer):
#     source_order = SourceOrderListSerializer(read_only=True)
#     source_order_id = serializers.PrimaryKeyRelatedField(
#         queryset=SourceOrder.objects.all(),
#         source='source_order',
#         write_only=True
#     )
#     hub = HubSerializer(read_only=True)
#     hub_id = serializers.PrimaryKeyRelatedField(
#         queryset=Hub.objects.all(),
#         source='hub',
#         write_only=True
#     )
#     received_by = UserSerializer(read_only=True)
#     condition_display = serializers.CharField(source='get_apparent_condition_display', read_only=True)

#     class Meta:
#         model = DeliveryRecord
#         fields = [
#             'id', 'source_order', 'source_order_id', 'hub', 'hub_id',
#             'received_by', 'received_at', 'driver_name', 'vehicle_number',
#             'apparent_condition', 'condition_display', 'notes', 'created_at'
#         ]
#         read_only_fields = ['id', 'received_by', 'received_at', 'created_at']

#     def create(self, validated_data):
#         """Create delivery record and update order status"""
#         validated_data['received_by'] = self.context['request'].user

#         with transaction.atomic():
#             delivery = super().create(validated_data)

#             # Update source order status
#             source_order = delivery.source_order
#             source_order.mark_delivered()

#             return delivery


# class WeighbridgeRecordSerializer(serializers.ModelSerializer):
#     source_order = SourceOrderListSerializer(read_only=True)
#     source_order_id = serializers.PrimaryKeyRelatedField(
#         queryset=SourceOrder.objects.all(),
#         source='source_order',
#         write_only=True
#     )
#     delivery = DeliveryRecordSerializer(read_only=True)
#     delivery_id = serializers.PrimaryKeyRelatedField(
#         queryset=DeliveryRecord.objects.all(),
#         source='delivery',
#         write_only=True
#     )
#     quality_grade = QualityGradeSerializer(read_only=True)
#     quality_grade_id = serializers.PrimaryKeyRelatedField(
#         queryset=QualityGrade.objects.all(),
#         source='quality_grade',
#         write_only=True
#     )
#     weighed_by = UserSerializer(read_only=True)

#     class Meta:
#         model = WeighbridgeRecord
#         fields = [
#             'id', 'source_order', 'source_order_id', 'delivery', 'delivery_id',
#             'weighed_by', 'weighed_at',
#             'gross_weight_kg', 'tare_weight_kg', 'net_weight_kg',
#             'moisture_level', 'quality_grade', 'quality_grade_id',
#             'quantity_variance_kg', 'notes', 'created_at'
#         ]
#         read_only_fields = [
#             'id', 'weighed_by', 'weighed_at', 'net_weight_kg',
#             'quantity_variance_kg', 'created_at'
#         ]

#     def create(self, validated_data):
#         """Create weighbridge record and update inventory"""
#         validated_data['weighed_by'] = self.context['request'].user

#         with transaction.atomic():
#             record = super().create(validated_data)

#             # Mark source order as completed
#             source_order = record.source_order
#             source_order.status = 'completed'
#             source_order.completed_at = timezone.now()
#             source_order.save(update_fields=['status', 'completed_at'])

#             # Update inventory
#             from vouchers.models import Inventory
#             inventory, created = Inventory.objects.get_or_create(
#                 hub=source_order.hub,
#                 grain_type=source_order.grain_type,
#                 defaults={
#                     'total_quantity_kg': Decimal('0.00'),
#                     'available_quantity_kg': Decimal('0.00')
#                 }
#             )
#             inventory.total_quantity_kg += record.net_weight_kg
#             inventory.available_quantity_kg += record.net_weight_kg
#             inventory.save()

#             return record

#     def to_representation(self, instance):
#         representation = super().to_representation(instance)
#         # Convert Decimal fields to float
#         decimal_fields = [
#             'gross_weight_kg', 'tare_weight_kg', 'net_weight_kg',
#             'moisture_level', 'quantity_variance_kg'
#         ]
#         for field in decimal_fields:
#             if representation.get(field) is not None:
#                 representation[field] = float(representation[field])
#         return representation


# class SupplierInvoiceSerializer(serializers.ModelSerializer):
#     source_order = SourceOrderListSerializer(read_only=True)
#     supplier = SupplierProfileSerializer(read_only=True)
#     payment_method = PaymentPreferenceSerializer(read_only=True)
#     status_display = serializers.CharField(source='get_status_display', read_only=True)
#     payments_list = serializers.SerializerMethodField()

#     class Meta:
#         model = SupplierInvoice
#         fields = [
#             'id', 'invoice_number', 'source_order', 'supplier',
#             'amount_due', 'amount_paid', 'balance_due',
#             'payment_method', 'payment_reference',
#             'status', 'status_display',
#             'issued_at', 'due_date', 'paid_at',
#             'notes', 'payments_list',
#             'created_at', 'updated_at'
#         ]
#         read_only_fields = [
#             'id', 'invoice_number', 'source_order', 'supplier',
#             'amount_due', 'amount_paid', 'balance_due', 'status',
#             'issued_at', 'paid_at', 'created_at', 'updated_at'
#         ]

#     def get_payments_list(self, obj):
#         from .serializers import SupplierPaymentSerializer
#         payments = obj.payments.all()
#         return SupplierPaymentSerializer(payments, many=True).data

#     def to_representation(self, instance):
#         representation = super().to_representation(instance)
#         # Convert Decimal fields to float
#         for field in ['amount_due', 'amount_paid', 'balance_due']:
#             if representation.get(field) is not None:
#                 representation[field] = float(representation[field])
#         return representation


# class SupplierPaymentSerializer(serializers.ModelSerializer):
#     supplier_invoice = serializers.PrimaryKeyRelatedField(
#         queryset=SupplierInvoice.objects.all()
#     )
#     source_order = serializers.PrimaryKeyRelatedField(read_only=True)
#     processed_by = UserSerializer(read_only=True)
#     status_display = serializers.CharField(source='get_status_display', read_only=True)
#     method_display = serializers.CharField(source='get_method_display', read_only=True)

#     class Meta:
#         model = SupplierPayment
#         fields = [
#             'id', 'payment_number', 'supplier_invoice', 'source_order',
#             'amount', 'method', 'method_display', 'reference_number',
#             'status', 'status_display', 'processed_by',
#             'created_at', 'completed_at', 'notes'
#         ]
#         read_only_fields = [
#             'id', 'payment_number', 'source_order', 'processed_by',
#             'created_at', 'completed_at'
#         ]

#     def create(self, validated_data):
#         """Create payment and update invoice"""
#         validated_data['processed_by'] = self.context['request'].user
#         validated_data['source_order'] = validated_data['supplier_invoice'].source_order

#         with transaction.atomic():
#             payment = super().create(validated_data)

#             # Update invoice amounts if payment is completed
#             if payment.status == 'completed':
#                 invoice = payment.supplier_invoice
#                 invoice.amount_paid += payment.amount
#                 invoice.update_payment_status()

#                 if not payment.completed_at:
#                     payment.completed_at = timezone.now()
#                     payment.save(update_fields=['completed_at'])

#             return payment

#     def to_representation(self, instance):
#         representation = super().to_representation(instance)
#         if representation.get('amount') is not None:
#             representation['amount'] = float(representation['amount'])
#         return representation


# class NotificationSerializer(serializers.ModelSerializer):
#     user = UserSerializer(read_only=True)
#     type_display = serializers.CharField(source='get_notification_type_display', read_only=True)

#     class Meta:
#         model = Notification
#         fields = [
#             'id', 'user', 'notification_type', 'type_display',
#             'title', 'message', 'related_object_type', 'related_object_id',
#             'is_read', 'created_at'
#         ]
#         read_only_fields = ['id', 'user', 'created_at']


# # Dashboard serializers
# class SupplierDashboardSerializer(serializers.Serializer):
#     """Dashboard data for suppliers"""
#     total_orders = serializers.IntegerField()
#     pending_orders = serializers.IntegerField()
#     completed_orders = serializers.IntegerField()
#     total_supplied_kg = serializers.DecimalField(max_digits=15, decimal_places=2)
#     total_earned = serializers.DecimalField(max_digits=15, decimal_places=2)
#     pending_payment = serializers.DecimalField(max_digits=15, decimal_places=2)
#     recent_orders = SourceOrderListSerializer(many=True)
#     recent_invoices = SupplierInvoiceSerializer(many=True)
#     unread_notifications = serializers.IntegerField()