# # trade/admin.py
# from django.contrib import admin
# from django.utils.html import format_html
# from django.urls import reverse
# from .models import (
#     Trade, TradeFinancing, TradeLoan, TradeCost, Brokerage, GoodsReceivedNote
# )


# @admin.register(Trade)
# class TradeAdmin(admin.ModelAdmin):
#     list_display = [
#         'trade_number', 'buyer_link', 'grain_type', 'net_tonnage',
#         'status_badge', 'payable_by_buyer', 'margin', 'roi_percentage',
#         'allocation_complete', 'requires_financing', 'created_at'
#     ]
#     list_filter = [
#         'status', 'grain_type', 'hub', 'allocation_complete',
#         'requires_financing', 'delivery_status', 'created_at'
#     ]
#     search_fields = ['trade_number', 'buyer__name', 'remarks', 'hub__name']
#     readonly_fields = [
#         'id', 'trade_number', 'grn_number',
#         'total_trade_cost', 'payable_by_buyer', 'margin',
#         'gross_margin_percentage', 'roi_percentage', 'created_at', 'updated_at'
#     ]
    
#     fieldsets = (
#         ('Basic Information', {
#             'fields': ('id', 'trade_number', 'grn_number', 'buyer', 'supplier', 'hub')
#         }),
#         ('Grain Details', {
#             'fields': ('grain_type', 'quality_grade')
#         }),
#         ('Quantities', {
#             'fields': (
#                 'gross_tonnage', 'net_tonnage',
#                 'quantity_kg', 'quantity_bags', 'bag_weight_kg'
#             )
#         }),
#         ('Pricing', {
#             'fields': ('buying_price', 'selling_price')
#         }),
#         ('Costs Breakdown', {
#             'fields': (
#                 'aflatoxin_qa_cost', 'weighbridge_cost', 'offloading_cost', 'loading_cost',
#                 'transport_cost_per_kg', 'financing_fee_percentage', 'financing_days',
#                 'git_insurance_percentage', 'deduction_percentage',
#                 'other_expenses', 'bennu_fees'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Calculated Totals', {
#             'fields': (
#                 'total_trade_cost', 'payable_by_buyer', 'margin',
#                 'gross_margin_percentage', 'roi_percentage'
#             )
#         }),
#         ('Payment Information', {
#             'fields': (
#                 'payment_due_date', 'payment_terms', 'payment_terms_days', 'credit_terms_days'
#             )
#         }),
#         ('Delivery Information', {
#             'fields': (
#                 'delivery_status', 'delivery_date', 'delivery_location',
#                 'delivery_distance_km', 'expected_delivery_date', 'actual_delivery_date'
#             )
#         }),
#         ('Vehicle & Transport', {
#             'fields': (
#                 'vehicle_number', 'driver_name', 'driver_id', 'driver_phone'
#             ),
#             'classes': ('collapse',)
#         }),
#         ('Status & Workflow', {
#             'fields': (
#                 'status', 'initiated_by', 'approved_by', 'approved_at',
#                 'allocation_complete', 'requires_financing', 'financing_complete'
#             )
#         }),
#         ('Notes', {
#             'fields': ('remarks', 'internal_notes', 'contract_notes'),
#             'classes': ('collapse',)
#         }),
#         ('Timestamps', {
#             'fields': ('created_at', 'updated_at', 'is_active'),
#             'classes': ('collapse',)
#         }),
#     )

#     def buyer_link(self, obj):
#         """Clickable buyer link in admin"""
#         url = reverse('admin:crm_account_change', args=[obj.buyer.id])
#         return format_html('<a href="{}">{}</a>', url, obj.buyer.name)
#     buyer_link.short_description = 'Buyer'

#     def status_badge(self, obj):
#         colors = {
#             'draft': 'gray',
#             'pending_approval': 'orange',
#             'approved': 'blue',
#             'pending_allocation': 'purple',
#             'allocated': 'teal',
#             'in_transit': 'indigo',
#             'delivered': 'green',
#             'completed': 'darkgreen',
#             'cancelled': 'red',
#             'rejected': 'darkred',
#         }
#         color = colors.get(obj.status, 'gray')
#         return format_html(
#             '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
#             color,
#             obj.get_status_display()
#         )
#     status_badge.short_description = 'Status'


# @admin.register(TradeFinancing)
# class TradeFinancingAdmin(admin.ModelAdmin):
#     list_display = [
#         'trade', 'investor_account', 'allocated_amount',
#         'allocation_percentage', 'investor_margin', 'allocation_date'
#     ]
#     list_filter = ['allocation_date', 'created_at']
#     search_fields = ['trade__trade_number', 'investor_account__investor__name']
#     readonly_fields = ['allocation_percentage', 'margin_earned', 'investor_margin', 'bennu_margin', 'created_at', 'updated_at']


# @admin.register(TradeLoan)
# class TradeLoanAdmin(admin.ModelAdmin):
#     list_display = [
#         'trade', 'investor_account', 'amount', 'interest_rate',
#         'status', 'due_date', 'amount_repaid', 'interest_earned'
#     ]
#     list_filter = ['status', 'due_date', 'created_at']
#     search_fields = ['trade__trade_number', 'investor_account__investor__name']
#     readonly_fields = ['interest_earned', 'created_at', 'updated_at']


# @admin.register(TradeCost)
# class TradeCostAdmin(admin.ModelAdmin):
#     list_display = ['trade', 'cost_type', 'amount', 'is_per_unit', 'created_at']
#     list_filter = ['is_per_unit', 'created_at']
#     search_fields = ['trade__trade_number', 'cost_type', 'description']


# @admin.register(Brokerage)
# class BrokerageAdmin(admin.ModelAdmin):
#     list_display = ['trade', 'agent', 'commission_type', 'commission_value', 'amount', 'created_at']
#     list_filter = ['commission_type', 'created_at']
#     search_fields = ['trade__trade_number', 'agent__first_name', 'agent__last_name']
#     readonly_fields = ['amount', 'created_at']


# @admin.register(GoodsReceivedNote)
# class GoodsReceivedNoteAdmin(admin.ModelAdmin):
#     list_display = [
#         'grn_number', 'trade', 'delivery_date', 'net_weight_kg',
#         'delivered_to_name', 'received_by_name', 'created_at'
#     ]
#     list_filter = ['delivery_date', 'loading_date', 'created_at']
#     search_fields = ['grn_number', 'trade__trade_number', 'vehicle_number', 'delivered_to_name']
#     readonly_fields = ['grn_number', 'created_at', 'updated_at']
    
#     fieldsets = (
#         ('Basic Information', {
#             'fields': ('grn_number', 'trade')
#         }),
#         ('Loading Details', {
#             'fields': ('point_of_loading', 'loading_date')
#         }),
#         ('Delivery Details', {
#             'fields': (
#                 'delivery_date', 'delivered_to_name',
#                 'delivered_to_address', 'delivered_to_contact'
#             )
#         }),
#         ('Vehicle & Driver', {
#             'fields': ('vehicle_number', 'driver_name', 'driver_id_number', 'driver_phone')
#         }),
#         ('Weight Details', {
#             'fields': ('quantity_bags', 'gross_weight_kg', 'tare_weight_kg', 'net_weight_kg')
#         }),
#         ('Signatures', {
#             'fields': (
#                 'warehouse_manager_name', 'warehouse_manager_signature', 'warehouse_manager_date',
#                 'received_by_name', 'received_by_signature', 'received_by_date'
#             )
#         }),
#         ('Additional Information', {
#             'fields': ('remarks', 'reason')
#         }),
#         ('Timestamps', {
#             'fields': ('created_at', 'updated_at')
#         }),
#     )
