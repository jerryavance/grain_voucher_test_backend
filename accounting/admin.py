# accounting/admin.py - FIXED FOR SIMPLIFIED INVOICING
from django.contrib import admin
from .models import Invoice, Payment, JournalEntry, Budget, InvoiceBatch


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_number', 'account', 'grn', 'issue_date', 'due_date',
        'total_amount', 'amount_paid', 'amount_due', 'status', 'payment_status'
    ]
    list_filter = [
        'status', 'payment_status', 'issue_date', 'due_date', 'account'
    ]
    search_fields = [
        'invoice_number', 'account__name', 'grn__grn_number',
        'trade__trade_number', 'notes'
    ]
    readonly_fields = [
        'invoice_number', 'subtotal', 'tax_amount', 'total_amount',
        'amount_paid', 'amount_due', 'payment_status',
        'batch_sent_date', 'batch_id', 'created_at', 'updated_at'
    ]
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'invoice_number', 'account', 'grn', 'trade', 'status', 'payment_status'
            )
        }),
        ('Dates', {
            'fields': (
                'issue_date', 'due_date', 'delivery_date'
            )
        }),
        ('Item Details (from GRN)', {
            'fields': (
                'description', 'grain_type', 'quality_grade', 'supplier_name',
                'quantity_kg', 'unit_price'
            )
        }),
        ('Amounts', {
            'fields': (
                'subtotal', 'bennu_fees', 'logistics_cost', 'weighbridge_cost',
                'other_charges', 'tax_rate', 'tax_amount', 'discount_amount',
                'total_amount', 'amount_paid', 'amount_due'
            )
        }),
        ('Bank Details', {
            'fields': (
                'beneficiary_bank', 'beneficiary_name',
                'beneficiary_account', 'beneficiary_branch'
            ),
            'classes': ('collapse',)
        }),
        ('Terms & Notes', {
            'fields': ('payment_terms', 'notes', 'internal_notes')
        }),
        ('Batch Sending', {
            'fields': ('batch_id', 'batch_sent_date'),
            'classes': ('collapse',)
        }),
        ('Tracking', {
            'fields': (
                'created_by', 'last_reminder_sent',
                'created_at', 'updated_at'
            ),
            'classes': ('collapse',)
        })
    )
    date_hierarchy = 'issue_date'

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj and obj.status != 'draft':
            readonly.extend([
                'account', 'grn', 'trade', 'issue_date', 'due_date',
                'delivery_date', 'description', 'grain_type', 'quality_grade',
                'supplier_name', 'quantity_kg', 'unit_price', 'subtotal',
                'bennu_fees', 'logistics_cost', 'weighbridge_cost',
                'other_charges', 'tax_rate', 'discount_amount'
            ])
        return readonly

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'payment_number', 'invoice', 'amount', 'payment_date',
        'payment_method', 'status', 'reconciled'
    ]
    list_filter = [
        'status', 'payment_method', 'reconciled', 'payment_date'
    ]
    search_fields = [
        'payment_number', 'invoice__invoice_number',
        'reference_number', 'transaction_id', 'notes'
    ]
    readonly_fields = [
        'payment_number', 'account', 'reconciled_date',
        'reconciled_by', 'created_by', 'created_at', 'updated_at'
    ]
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'payment_number', 'invoice', 'account', 'status'
            )
        }),
        ('Payment Details', {
            'fields': (
                'amount', 'payment_date', 'payment_method',
                'reference_number', 'transaction_id'
            )
        }),
        ('Notes', {
            'fields': ('notes', 'internal_notes')
        }),
        ('Reconciliation', {
            'fields': (
                'reconciled', 'reconciled_date', 'reconciled_by'
            ),
            'classes': ('collapse',)
        }),
        ('Tracking', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    date_hierarchy = 'payment_date'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
            obj.account = obj.invoice.account
        if obj.reconciled and not obj.reconciled_by:
            obj.reconciled_by = request.user
            from django.utils import timezone
            obj.reconciled_date = timezone.now()
        super().save_model(request, obj, form, change)

    actions = ['mark_as_completed', 'mark_as_reconciled']

    def mark_as_completed(self, request, queryset):
        count = queryset.update(status='completed')
        self.message_user(request, f'{count} payment(s) marked as completed.')
    mark_as_completed.short_description = 'Mark as Completed'

    def mark_as_reconciled(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status='completed').update(
            reconciled=True,
            reconciled_by=request.user,
            reconciled_date=timezone.now()
        )
        self.message_user(request, f'{count} payment(s) marked as reconciled.')
    mark_as_reconciled.short_description = 'Mark as Reconciled'


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = [
        'entry_number', 'entry_type', 'entry_date',
        'debit_account', 'credit_account', 'amount', 'is_reversed'
    ]
    list_filter = ['entry_type', 'entry_date', 'is_reversed']
    search_fields = ['entry_number', 'description', 'debit_account', 'credit_account']
    readonly_fields = ['entry_number', 'reversed_by', 'created_by', 'created_at']
    date_hierarchy = 'entry_date'

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:
            readonly.extend([
                'entry_type', 'entry_date', 'debit_account',
                'credit_account', 'amount', 'description',
                'related_trade', 'related_invoice', 'related_payment'
            ])
        return readonly

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InvoiceBatch)
class InvoiceBatchAdmin(admin.ModelAdmin):
    list_display = ['batch_number', 'account', 'batch_date', 'invoice_count', 'total_amount', 'sent_via_email']
    list_filter = ['sent_via_email', 'batch_date', 'account']
    search_fields = ['batch_number', 'account__name']
    readonly_fields = ['batch_number', 'created_by', 'created_at']
    date_hierarchy = 'batch_date'


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = [
        'period', 'hub', 'grain_type', 'budgeted_amount',
        'actual_amount', 'variance_display', 'is_over_budget'
    ]
    list_filter = ['period', 'hub', 'grain_type']
    search_fields = ['hub__name', 'grain_type__name']
    readonly_fields = ['actual_amount', 'created_at', 'updated_at']
    date_hierarchy = 'period'

    def variance_display(self, obj):
        variance = obj.variance()
        color = 'green' if variance >= 0 else 'red'
        return f'<span style="color: {color};">{variance:,.2f}</span>'
    variance_display.short_description = 'Variance'
    variance_display.allow_tags = True

    def is_over_budget(self, obj):
        return 'Over' if obj.is_over_budget() else 'On Track'
    is_over_budget.short_description = 'Budget Status'


# Customize admin header
admin.site.site_header = 'BENNU Accounting Administration'
admin.site.site_title = 'BENNU Accounting'
admin.site.index_title = 'Accounting Management'