# crm/admin.py
from django.contrib import admin
from .models import Lead, Account, Contact, Opportunity, Contract

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'credit_terms_days', 'hub', 'created_at', 'is_active']
    list_filter = ['type', 'is_active', 'hub']
    search_fields = ['name']
    ordering = ['name']

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'email', 'status', 'assigned_to', 'created_at', 'is_active']
    list_filter = ['status', 'is_active']
    search_fields = ['name', 'phone', 'email']
    ordering = ['-created_at']

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['name', 'account', 'phone', 'email', 'role', 'created_at']
    list_filter = ['account']
    search_fields = ['name', 'phone', 'email', 'role']
    ordering = ['name']

@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ['name', 'account', 'stage', 'expected_volume_mt', 'expected_price_per_mt', 'assigned_to', 'created_at']
    list_filter = ['stage', 'account']
    search_fields = ['name']
    ordering = ['-created_at']

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['opportunity', 'status', 'signed_at', 'created_at']
    list_filter = ['status']
    search_fields = ['opportunity__name']
    ordering = ['-created_at']