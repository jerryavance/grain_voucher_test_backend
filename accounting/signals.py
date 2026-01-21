# accounting/signals.py - FIXED VERSION

from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
import traceback

from trade.models import GoodsReceivedNote
from .models import Invoice, Payment, JournalEntry


@receiver(post_save, sender=GoodsReceivedNote)
def create_invoice_on_grn(sender, instance, created, **kwargs):
    """
    ✅ FIXED: Create invoice immediately when GRN is created
    Removed transaction.on_commit to ensure invoice is created in same transaction
    """
    if not created:
        return
    
    print(f"🔔 Signal triggered for GRN: {instance.grn_number}")
    
    # Create invoice immediately
    try:
        _create_invoice_for_grn(instance)
    except Exception as e:
        print(f"❌ Error in signal handler: {str(e)}")
        traceback.print_exc()


def _create_invoice_for_grn(grn):
    """
    Create invoice for GRN
    """
    trade = grn.trade
    
    print(f"📝 Creating invoice for GRN {grn.grn_number}, Trade {trade.trade_number}")
    
    try:
        # Check if invoice already exists (prevent duplicates)
        existing_invoice = Invoice.objects.filter(grn=grn).first()
        if existing_invoice:
            print(f"⚠️ Invoice already exists for GRN {grn.grn_number}: {existing_invoice.invoice_number}")
            return
        
        # Create invoice
        invoice = Invoice(
            grn=grn,
            trade=trade,
            account=trade.buyer,
            issue_date=timezone.now().date(),
            delivery_date=grn.delivery_date,
            status='issued',
            created_by=trade.approved_by
        )
        
        # Populate from GRN
        invoice.populate_from_grn()
        
        # Save invoice (this triggers calculate_amounts in the save method)
        invoice.save()
        
        print(f"✅ Invoice created: {invoice.invoice_number} for GRN {grn.grn_number}")
        print(f"   - Amount: {invoice.total_amount}")
        print(f"   - Buyer: {invoice.account.name}")
        
        # Create journal entry
        try:
            journal_entry = JournalEntry.objects.create(
                entry_type='sale',
                entry_date=invoice.issue_date,
                debit_account='Accounts Receivable',
                credit_account='Sales Revenue',
                amount=invoice.total_amount,
                related_trade=trade,
                related_invoice=invoice,
                description=f"Invoice {invoice.invoice_number} for GRN {grn.grn_number}",
                notes=f"Delivery to {trade.buyer.name} on {grn.delivery_date}",
                created_by=trade.approved_by
            )
            print(f"✅ Journal entry created: {journal_entry.entry_number}")
        except Exception as e:
            print(f"⚠️ Failed to create journal entry: {str(e)}")
            # Don't fail the whole process if journal entry fails
        
    except Exception as e:
        print(f"❌ Error creating invoice for GRN {grn.grn_number}: {str(e)}")
        traceback.print_exc()
        raise  # Re-raise to see the error in the API response


@receiver(post_save, sender=Payment)
def update_invoice_on_payment(sender, instance, created, **kwargs):
    """Update invoice when payment is made"""
    if not created or instance.status != 'completed':
        return
    
    invoice = instance.invoice
    
    print(f"💰 Payment received for invoice {invoice.invoice_number}: {instance.amount}")
    
    with transaction.atomic():
        # Recalculate amounts
        from django.db.models import Sum
        total_paid = invoice.payments.filter(
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        invoice.amount_paid = total_paid
        invoice.amount_due = invoice.total_amount - total_paid
        
        # Update payment status
        invoice.update_payment_status()
        invoice.save(update_fields=['amount_paid', 'amount_due', 'payment_status', 'status'])
        
        print(f"✅ Invoice {invoice.invoice_number} updated: paid {invoice.amount_paid}/{invoice.total_amount}")


@receiver(post_save, sender=Payment)
def create_payment_journal_entry(sender, instance, created, **kwargs):
    """Create journal entry for payment"""
    if not created or instance.status != 'completed':
        return
    
    # Check if journal entry already exists
    existing = JournalEntry.objects.filter(
        related_payment=instance,
        entry_type='payment'
    ).exists()
    
    if existing:
        return
    
    invoice = instance.invoice
    trade = invoice.trade
    
    debit_account_map = {
        'cash': 'Cash',
        'bank_transfer': 'Bank Account',
        'mobile_money': 'Mobile Money Account',
        'cheque': 'Bank Account',
        'credit_card': 'Bank Account',
        'other': 'Cash'
    }
    debit_account = debit_account_map.get(instance.payment_method, 'Bank Account')
    
    JournalEntry.objects.create(
        entry_type='payment',
        entry_date=instance.payment_date,
        debit_account=debit_account,
        credit_account='Accounts Receivable',
        amount=instance.amount,
        related_invoice=invoice,
        related_payment=instance,
        related_trade=trade,
        description=f"Payment {instance.payment_number} for invoice {invoice.invoice_number}",
        notes=f"Method: {instance.get_payment_method_display()}, Ref: {instance.reference_number or 'N/A'}",
        created_by=instance.created_by
    )


@receiver(post_save, sender=Payment)
def check_trade_completion(sender, instance, created, **kwargs):
    """
    Mark trade as completed when ALL invoices are paid
    """
    if instance.status != 'completed':
        return
    
    invoice = instance.invoice
    trade = invoice.trade
    
    # Check if ALL invoices for this trade are paid
    all_invoices_paid = not Invoice.objects.filter(
        trade=trade,
        payment_status__in=['unpaid', 'partial', 'overdue']
    ).exists()
    
    if all_invoices_paid and trade.status == 'delivered':
        trade.status = 'completed'
        trade.save(update_fields=['status'])
        print(f"✅ Trade {trade.trade_number} completed - all invoices paid")



# # accounting/signals.py - CORRECTED WITH TRANSACTION SAFETY

# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from decimal import Decimal
# from django.utils import timezone
# from django.db import transaction

# from trade.models import GoodsReceivedNote
# from .models import Invoice, Payment, JournalEntry


# @receiver(post_save, sender=GoodsReceivedNote)
# def create_invoice_on_grn(sender, instance, created, **kwargs):
#     """
#     ✅ ENHANCED: Create invoice with transaction safety
#     Uses transaction.on_commit to ensure GRN is fully saved first
#     """
#     if not created:
#         return
    
#     # Use on_commit to ensure GRN is fully saved before creating invoice
#     transaction.on_commit(lambda: _create_invoice_for_grn(instance))


# def _create_invoice_for_grn(grn):
#     """
#     Separate function to create invoice (called after transaction commit)
#     This prevents race conditions and orphaned invoices
#     """
#     trade = grn.trade
    
#     try:
#         with transaction.atomic():
#             # Check if invoice already exists (prevent duplicates)
#             if hasattr(grn, 'invoice') and grn.invoice:
#                 print(f"⚠️ Invoice already exists for GRN {grn.grn_number}")
#                 return
            
#             # Create invoice
#             invoice = Invoice.objects.create(
#                 grn=grn,
#                 trade=trade,
#                 account=trade.buyer,
#                 issue_date=timezone.now().date(),
#                 delivery_date=grn.delivery_date,
#                 status='issued',
#                 created_by=trade.approved_by
#             )
            
#             # Populate from GRN and trade
#             invoice.populate_from_grn()
#             invoice.save()
            
#             # Create journal entry
#             JournalEntry.objects.create(
#                 entry_type='sale',
#                 entry_date=invoice.issue_date,
#                 debit_account='Accounts Receivable',
#                 credit_account='Sales Revenue',
#                 amount=invoice.total_amount,
#                 related_trade=trade,
#                 related_invoice=invoice,
#                 description=f"Invoice {invoice.invoice_number} for GRN {grn.grn_number}",
#                 notes=f"Delivery to {trade.buyer.name} on {grn.delivery_date}",
#                 created_by=trade.approved_by
#             )
            
#             print(f"✅ Invoice {invoice.invoice_number} created for GRN {grn.grn_number}")
            
#     except Exception as e:
#         print(f"❌ Error creating invoice for GRN {grn.grn_number}: {str(e)}")
#         import traceback
#         traceback.print_exc()


# @receiver(post_save, sender=Payment)
# def update_invoice_on_payment(sender, instance, created, **kwargs):
#     """Update invoice when payment is made"""
#     if not created or instance.status != 'completed':
#         return
    
#     invoice = instance.invoice
    
#     with transaction.atomic():
#         # Recalculate amounts
#         from django.db.models import Sum
#         total_paid = invoice.payments.filter(
#             status='completed'
#         ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
#         invoice.amount_paid = total_paid
#         invoice.amount_due = invoice.total_amount - total_paid
        
#         # Update payment status
#         invoice.update_payment_status()
#         invoice.save(update_fields=['amount_paid', 'amount_due', 'payment_status', 'status'])
        
#         print(f"✅ Invoice {invoice.invoice_number} updated: paid {invoice.amount_paid}/{invoice.total_amount}")


# @receiver(post_save, sender=Payment)
# def create_payment_journal_entry(sender, instance, created, **kwargs):
#     """Create journal entry for payment"""
#     if not created or instance.status != 'completed':
#         return
    
#     # Check if journal entry already exists
#     existing = JournalEntry.objects.filter(
#         related_payment=instance,
#         entry_type='payment'
#     ).exists()
    
#     if existing:
#         return
    
#     invoice = instance.invoice
#     trade = invoice.trade
    
#     debit_account_map = {
#         'cash': 'Cash',
#         'bank_transfer': 'Bank Account',
#         'mobile_money': 'Mobile Money Account',
#         'cheque': 'Bank Account',
#         'credit_card': 'Bank Account',
#         'other': 'Cash'
#     }
#     debit_account = debit_account_map.get(instance.payment_method, 'Bank Account')
    
#     JournalEntry.objects.create(
#         entry_type='payment',
#         entry_date=instance.payment_date,
#         debit_account=debit_account,
#         credit_account='Accounts Receivable',
#         amount=instance.amount,
#         related_invoice=invoice,
#         related_payment=instance,
#         related_trade=trade,
#         description=f"Payment {instance.payment_number} for invoice {invoice.invoice_number}",
#         notes=f"Method: {instance.get_payment_method_display()}, Ref: {instance.reference_number or 'N/A'}",
#         created_by=instance.created_by
#     )


# @receiver(post_save, sender=Payment)
# def check_trade_completion(sender, instance, created, **kwargs):
#     """
#     Mark trade as completed when ALL invoices are paid
#     """
#     if instance.status != 'completed':
#         return
    
#     invoice = instance.invoice
#     trade = invoice.trade
    
#     # Check if ALL invoices for this trade are paid
#     all_invoices_paid = not Invoice.objects.filter(
#         trade=trade,
#         payment_status__in=['unpaid', 'partial', 'overdue']
#     ).exists()
    
#     if all_invoices_paid and trade.status == 'delivered':
#         trade.status = 'completed'
#         trade.save(update_fields=['status'])
#         print(f"✅ Trade {trade.trade_number} completed - all invoices paid")