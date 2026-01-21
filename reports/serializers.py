# reports/serializers.py - FULLY FIXED VERSION WITH BOOLEAN NULL HANDLING
from rest_framework import serializers
from .models import ReportExport, ReportSchedule
from authentication.serializers import UserSerializer
from hubs.serializers import HubSerializer


class ReportExportSerializer(serializers.ModelSerializer):
    generated_by = UserSerializer(read_only=True)
    hub = HubSerializer(read_only=True)
    report_type_display = serializers.CharField(source='get_report_type_display', read_only=True)
    format_display = serializers.CharField(source='get_format_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_expired = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ReportExport
        fields = [
            'id', 'report_type', 'report_type_display', 'format', 'format_display',
            'filters', 'file_path', 'file_size', 'status', 'status_display',
            'error_message', 'generated_by', 'hub', 'requested_at',
            'completed_at', 'expires_at', 'record_count', 'is_expired', 'download_url'
        ]
        read_only_fields = [
            'id', 'file_path', 'file_size', 'status', 'error_message',
            'generated_by', 'requested_at', 'completed_at', 'record_count'
        ]
    
    def get_is_expired(self, obj):
        return obj.is_expired()
    
    def get_download_url(self, obj):
        if obj.status == 'completed' and not obj.is_expired():
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(f'/api/reports/exports/{obj.id}/download/')
        return None


class ReportScheduleSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    hub = HubSerializer(read_only=True)
    recipients = UserSerializer(many=True, read_only=True)
    recipient_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False
    )
    hub_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    
    frequency_display = serializers.CharField(source='get_frequency_display', read_only=True)
    report_type_display = serializers.CharField(source='get_report_type_display', read_only=True)
    
    class Meta:
        model = ReportSchedule
        fields = [
            'id', 'name', 'report_type', 'report_type_display', 'format',
            'frequency', 'frequency_display', 'day_of_week', 'day_of_month',
            'time_of_day', 'filters', 'recipients', 'recipient_ids', 'is_active',
            'hub', 'hub_id', 'created_by', 'created_at', 'updated_at',
            'last_run', 'next_run'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at', 'last_run', 'next_run']
    
    def validate(self, data):
        frequency = data.get('frequency')
        if frequency == 'weekly' and not data.get('day_of_week'):
            raise serializers.ValidationError({'day_of_week': 'Required for weekly schedules'})
        if frequency == 'monthly' and not data.get('day_of_month'):
            raise serializers.ValidationError({'day_of_month': 'Required for monthly schedules'})
        return data
    
    def create(self, validated_data):
        recipient_ids = validated_data.pop('recipient_ids', [])
        hub_id = validated_data.pop('hub_id', None)
        if hub_id:
            from hubs.models import Hub
            validated_data['hub'] = Hub.objects.get(id=hub_id)
        validated_data['created_by'] = self.context['request'].user
        schedule = super().create(validated_data)
        if recipient_ids:
            from authentication.models import GrainUser
            recipients = GrainUser.objects.filter(id__in=recipient_ids)
            schedule.recipients.set(recipients)
        return schedule


class ReportFilterSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    hub_id = serializers.UUIDField(required=False, allow_null=True)


# ✅ FIXED: All boolean fields with proper null handling
class SupplierReportFilterSerializer(ReportFilterSerializer):
    supplier_id = serializers.UUIDField(required=False, allow_null=True)
    grain_type_id = serializers.UUIDField(required=False, allow_null=True)
    min_total_supplied = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)


class TradeReportFilterSerializer(ReportFilterSerializer):
    status = serializers.MultipleChoiceField(
        choices=['draft', 'pending_approval', 'approved', 'pending_allocation', 'ready_for_delivery',
                 'in_transit', 'delivered', 'completed', 'cancelled', 'rejected'],
        required=False,
        allow_empty=True,
        default=list
    )
    buyer_id = serializers.UUIDField(required=False, allow_null=True)
    supplier_id = serializers.UUIDField(required=False, allow_null=True)
    grain_type_id = serializers.UUIDField(required=False, allow_null=True)
    min_value = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, allow_null=True)
    max_value = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, allow_null=True)


class InvoiceReportFilterSerializer(ReportFilterSerializer):
    payment_status = serializers.MultipleChoiceField(
        choices=['unpaid', 'partial', 'paid', 'overdue'],
        required=False,
        allow_empty=True,
        default=list
    )
    account_id = serializers.UUIDField(required=False, allow_null=True)
    min_amount = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, allow_null=True)
    # ✅ FIX: Allow null and provide default value
    overdue_only = serializers.BooleanField(required=False, default=False, allow_null=True)
    
    def validate_overdue_only(self, value):
        """Convert None to False"""
        return value if value is not None else False


class PaymentReportFilterSerializer(ReportFilterSerializer):
    payment_method = serializers.MultipleChoiceField(
        choices=['cash', 'bank_transfer', 'mobile_money', 'cheque', 'credit_card', 'other'],
        required=False,
        allow_empty=True,
        default=list
    )
    account_id = serializers.UUIDField(required=False, allow_null=True)
    min_amount = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, allow_null=True)


class DepositorReportFilterSerializer(ReportFilterSerializer):
    farmer_id = serializers.UUIDField(required=False, allow_null=True)
    grain_type_id = serializers.UUIDField(required=False, allow_null=True)
    # ✅ FIX: Allow null and provide default value
    validated_only = serializers.BooleanField(required=False, default=False, allow_null=True)
    min_total_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    
    def validate_validated_only(self, value):
        """Convert None to False"""
        return value if value is not None else False


class VoucherReportFilterSerializer(ReportFilterSerializer):
    status = serializers.MultipleChoiceField(
        choices=['pending_verification', 'issued', 'transferred', 'redeemed', 'expired'],
        required=False,
        allow_empty=True,
        default=list
    )
    verification_status = serializers.MultipleChoiceField(
        choices=['verified', 'pending', 'rejected'],
        required=False,
        allow_empty=True,
        default=list
    )
    holder_id = serializers.UUIDField(required=False, allow_null=True)
    grain_type_id = serializers.UUIDField(required=False, allow_null=True)


class InventoryReportFilterSerializer(ReportFilterSerializer):
    grain_type_id = serializers.UUIDField(required=False, allow_null=True)
    min_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    # ✅ FIX: Allow null and provide default value
    low_stock_only = serializers.BooleanField(required=False, default=False, allow_null=True)
    
    def validate_low_stock_only(self, value):
        """Convert None to False"""
        return value if value is not None else False


class InvestorReportFilterSerializer(ReportFilterSerializer):
    investor_id = serializers.UUIDField(required=False, allow_null=True)
    min_total_invested = serializers.DecimalField(max_digits=15, decimal_places=2, required=False, allow_null=True)
    include_performance = serializers.BooleanField(required=False, default=True)