# vouchers/admin.py
from django.contrib import admin
from .models import (
    GrainType, QualityGrade, PriceFeed, Deposit, Voucher,
    Redemption, PurchaseOffer, Inventory, LedgerEntry
)

@admin.register(GrainType)
class GrainTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)
    list_filter = ('name',)

@admin.register(QualityGrade)
class QualityGradeAdmin(admin.ModelAdmin):
    list_display = ('name', 'min_moisture', 'max_moisture', 'description')
    search_fields = ('name',)
    list_filter = ('name',)

@admin.register(PriceFeed)
class PriceFeedAdmin(admin.ModelAdmin):
    list_display = ('grain_type', 'hub', 'price_per_kg', 'effective_date', 'created_at', 'updated_at')
    search_fields = ('grain_type__name', 'hub__name')
    list_filter = ('grain_type', 'hub', 'effective_date')
    date_hierarchy = 'effective_date'

@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ('id', 'farmer', 'hub', 'grain_type', 'quantity_kg', 'deposit_date', 'validated')
    search_fields = ('farmer__phone_number', 'hub__name', 'grn_number')
    list_filter = ('hub', 'grain_type', 'deposit_date', 'validated')
    date_hierarchy = 'deposit_date'

@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ('id', 'deposit', 'holder', 'status', 'issue_date', 'current_value')
    search_fields = ('holder__phone_number', 'deposit__grn_number')
    list_filter = ('status', 'issue_date')
    date_hierarchy = 'issue_date'

@admin.register(Redemption)
class RedemptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'voucher', 'requester', 'amount', 'status', 'request_date')
    search_fields = ('voucher__id', 'requester__phone_number')
    list_filter = ('status', 'request_date', 'payment_method')
    date_hierarchy = 'request_date'

@admin.register(PurchaseOffer)
class PurchaseOfferAdmin(admin.ModelAdmin):
    list_display = ('id', 'investor', 'voucher', 'offer_price', 'status', 'offer_date')
    search_fields = ('investor__phone_number', 'voucher__id')
    list_filter = ('status', 'offer_date')
    date_hierarchy = 'offer_date'

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('hub', 'grain_type', 'total_quantity_kg', 'available_quantity_kg', 'last_updated')
    search_fields = ('hub__name', 'grain_type__name')
    list_filter = ('hub', 'grain_type')

@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'event_type', 'user', 'hub', 'amount', 'timestamp')
    search_fields = ('user__phone_number', 'hub__name', 'description')
    list_filter = ('event_type', 'timestamp', 'hub')
    date_hierarchy = 'timestamp'