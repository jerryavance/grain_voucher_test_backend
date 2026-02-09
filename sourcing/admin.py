# sourcing/admin.py
from django.contrib import admin
from .models import (
    SupplierProfile, PaymentPreference, SourceOrder, SupplierInvoice,
    DeliveryRecord, WeighbridgeRecord, SupplierPayment, Notification
)


@admin.register(SupplierProfile)
class SupplierProfileAdmin(admin.ModelAdmin):
    list_display = ['business_name', 'user', 'hub', 'is_verified', 'created_at']
    list_filter = ['is_verified', 'hub', 'created_at']
    search_fields = ['business_name', 'user__phone_number', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at', 'updated_at', 'verified_at']
    filter_horizontal = ['typical_grain_types']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'hub', 'business_name', 'farm_location')
        }),
        ('Grain Types', {
            'fields': ('typical_grain_types',)
        }),
        ('Verification', {
            'fields': ('is_verified', 'verified_by', 'verified_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PaymentPreference)
class PaymentPreferenceAdmin(admin.ModelAdmin):
    list_display = ['supplier', 'method', 'is_default', 'is_active', 'created_at']
    list_filter = ['method', 'is_default', 'is_active', 'created_at']
    search_fields = ['supplier__business_name', 'supplier__user__phone_number']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(SourceOrder)
class SourceOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'supplier', 'grain_type', 'quantity_kg', 'total_cost', 'status', 'created_at']
    list_filter = ['status', 'grain_type', 'hub', 'logistics_type', 'created_at']
    search_fields = ['order_number', 'supplier__business_name', 'supplier__user__phone_number']
    readonly_fields = ['order_number', 'grain_cost', 'total_cost', 'created_at', 'sent_at', 'accepted_at', 'shipped_at', 'delivered_at', 'completed_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'supplier', 'hub', 'created_by', 'status')
        }),
        ('Grain Details', {
            'fields': ('grain_type', 'quantity_kg', 'offered_price_per_kg')
        }),
        ('Costs', {
            'fields': ('grain_cost', 'weighbridge_cost', 'logistics_cost', 'handling_cost', 'other_costs', 'total_cost')
        }),
        ('Payment', {
            'fields': ('payment_method',)
        }),
        ('Logistics', {
            'fields': ('logistics_type', 'driver_name', 'driver_phone', 'expected_delivery_date')
        }),
        ('Dates', {
            'fields': ('created_at', 'sent_at', 'accepted_at', 'shipped_at', 'delivered_at', 'completed_at'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )


@admin.register(SupplierInvoice)
class SupplierInvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'supplier', 'amount_due', 'amount_paid', 'balance_due', 'status', 'issued_at']
    list_filter = ['status', 'issued_at', 'due_date']
    search_fields = ['invoice_number', 'source_order__order_number', 'supplier__business_name']
    readonly_fields = ['invoice_number', 'amount_due', 'amount_paid', 'balance_due', 'issued_at', 'paid_at', 'created_at', 'updated_at']
    date_hierarchy = 'issued_at'
    
    fieldsets = (
        ('Invoice Information', {
            'fields': ('invoice_number', 'source_order', 'supplier', 'status')
        }),
        ('Amounts', {
            'fields': ('amount_due', 'amount_paid', 'balance_due')
        }),
        ('Payment Details', {
            'fields': ('payment_method', 'payment_reference')
        }),
        ('Dates', {
            'fields': ('issued_at', 'due_date', 'paid_at', 'created_at', 'updated_at')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )


@admin.register(DeliveryRecord)
class DeliveryRecordAdmin(admin.ModelAdmin):
    list_display = ['source_order', 'hub', 'received_by', 'received_at', 'apparent_condition']
    list_filter = ['hub', 'apparent_condition', 'received_at']
    search_fields = ['source_order__order_number', 'driver_name', 'vehicle_number']
    readonly_fields = ['received_at', 'created_at']
    date_hierarchy = 'received_at'


@admin.register(WeighbridgeRecord)
class WeighbridgeRecordAdmin(admin.ModelAdmin):
    list_display = ['source_order', 'net_weight_kg', 'quality_grade', 'moisture_level', 'quantity_variance_kg', 'weighed_at']
    list_filter = ['quality_grade', 'weighed_at']
    search_fields = ['source_order__order_number']
    readonly_fields = ['net_weight_kg', 'quantity_variance_kg', 'weighed_at', 'created_at']
    date_hierarchy = 'weighed_at'
    
    fieldsets = (
        ('Order Information', {
            'fields': ('source_order', 'delivery', 'weighed_by', 'weighed_at')
        }),
        ('Weights', {
            'fields': ('gross_weight_kg', 'tare_weight_kg', 'net_weight_kg', 'quantity_variance_kg')
        }),
        ('Quality', {
            'fields': ('moisture_level', 'quality_grade')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_number', 'supplier_invoice', 'amount', 'method', 'status', 'created_at']
    list_filter = ['status', 'method', 'created_at']
    search_fields = ['payment_number', 'reference_number', 'supplier_invoice__invoice_number']
    readonly_fields = ['payment_number', 'source_order', 'created_at', 'completed_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('payment_number', 'supplier_invoice', 'source_order', 'status')
        }),
        ('Details', {
            'fields': ('amount', 'method', 'reference_number', 'processed_by')
        }),
        ('Dates', {
            'fields': ('created_at', 'completed_at')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['user__phone_number', 'title', 'message']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Notification', {
            'fields': ('user', 'notification_type', 'title', 'message', 'is_read')
        }),
        ('Related Object', {
            'fields': ('related_object_type', 'related_object_id'),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        }),
    )