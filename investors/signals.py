# investors/signals.py - FIXED VERSION
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
from .models import InvestorAccount, InvestorDeposit, ProfitSharingAgreement
from trade.models import Trade, TradeFinancing
from vouchers.models import LedgerEntry


@receiver(post_save, sender=Trade)
def handle_trade_profit_allocation(sender, instance, created, **kwargs):
    """
    ✅ FIXED: When a Trade is completed and ALL invoices are paid, distribute profits to investors
    based on their financing allocations and applicable profit-sharing agreements.
    
    Trade can have MULTIPLE invoices (one per GRN/delivery).
    """
    # Skip if this is a new trade creation
    if created:
        return
    
    # Only process completed trades
    if instance.status != 'completed':
        return
    
    # ✅ FIX: Check if ALL invoices for this trade are paid
    from accounting.models import Invoice
    
    # Get all invoices for this trade
    invoices = Invoice.objects.filter(trade=instance)
    
    # If no invoices exist yet, return
    if not invoices.exists():
        return
    
    # Check if ALL invoices are fully paid
    all_invoices_paid = all(
        invoice.payment_status == 'paid' 
        for invoice in invoices
    )
    
    if not all_invoices_paid:
        return
    
    # Check if already processed (avoid duplicate processing)
    if hasattr(instance, '_profit_allocated') and instance._profit_allocated:
        return

    # Process allocations only if there are financings
    financings = instance.financing_allocations.all()
    if not financings.exists():
        return

    with transaction.atomic():
        for financing in financings:
            # Skip if already processed
            if financing.margin_earned > 0:
                continue
                
            investor_account = financing.investor_account
            agreement = investor_account.profit_agreements.order_by('-effective_date').first()

            # Defaults if no agreement exists
            profit_threshold = agreement.profit_threshold if agreement else Decimal('2.00')
            investor_share = agreement.investor_share if agreement else Decimal('75.00')
            bennu_share = agreement.bennu_share if agreement else Decimal('25.00')

            # Calculate margins
            margin_percentage = (
                (instance.margin / instance.total_trade_cost * 100)
                if instance.total_trade_cost > 0
                else Decimal('0.00')
            )

            financing.margin_earned = (
                (instance.margin * financing.allocated_amount / instance.total_trade_cost)
                if instance.total_trade_cost > 0
                else Decimal('0.00')
            )

            # Apply profit-sharing logic
            if margin_percentage <= profit_threshold:
                financing.investor_margin = financing.margin_earned
                financing.bennu_margin = Decimal('0.00')
            else:
                financing.investor_margin = financing.margin_earned * investor_share / 100
                financing.bennu_margin = financing.margin_earned * bennu_share / 100

            financing.save()

            # Update investor account balances
            investor_account.total_margin_earned += financing.investor_margin
            investor_account.available_balance += financing.investor_margin
            investor_account.save()

            # Log investor margin
            LedgerEntry.objects.create(
                event_type='trade_profit',
                related_object_id=financing.id,
                user=investor_account.investor,
                hub=instance.hub,
                description=f"Investor margin of {financing.investor_margin} UGX from trade {instance.trade_number}",
                amount=financing.investor_margin,
            )

            # Log bennu profit if any
            if financing.bennu_margin > 0:
                LedgerEntry.objects.create(
                    event_type='bennu_profit',
                    related_object_id=financing.id,
                    user=None,
                    hub=instance.hub,
                    description=f"bennu margin of {financing.bennu_margin} UGX from trade {instance.trade_number}",
                    amount=financing.bennu_margin,
                )
        
        # Mark as processed to avoid duplicate processing
        instance._profit_allocated = True
        
        print(f"✅ Profit allocated for trade {instance.trade_number}")


@receiver(post_save, sender=InvestorAccount)
def create_default_profit_sharing(sender, instance, created, **kwargs):
    """
    Automatically create a default ProfitSharingAgreement when
    a new InvestorAccount is created and has none.
    """
    if created and not instance.profit_agreements.exists():
        ProfitSharingAgreement.objects.create(
            investor_account=instance,
            profit_threshold=Decimal('2.00'),
            investor_share=Decimal('75.00'),
            bennu_share=Decimal('25.00'),
            notes="Default profit sharing agreement",
        )


@receiver(post_save, sender=InvestorDeposit)
def handle_deposit_creation(sender, instance, created, **kwargs):
    """
    Log deposit creation to ledger
    """
    if created:
        LedgerEntry.objects.create(
            event_type='deposit',
            related_object_id=instance.id,
            user=instance.investor_account.investor,
            hub=None,
            description=f"Deposit of {instance.amount} UGX",
            amount=instance.amount
        )