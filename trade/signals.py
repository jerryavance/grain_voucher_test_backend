# trade/signals.py - UPDATED SECTIONS

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db import transaction
from decimal import Decimal
from django.utils import timezone

from .models import Trade, TradeFinancing, TradeLoan, GoodsReceivedNote
from vouchers.models import Inventory, LedgerEntry


@receiver(post_save, sender=Trade)
def handle_trade_status_changes(sender, instance, created, **kwargs):
    """Handle automated processes when trade status changes"""
    
    if created:
        # Create initial ledger entry
        LedgerEntry.objects.create(
            event_type='trade_created',
            related_object_id=instance.id,
            user=instance.initiated_by,
            hub=instance.hub,
            timestamp=timezone.now(),
            description=f"Trade {instance.trade_number} created for {instance.buyer.name} - {instance.quantity_kg}kg {instance.grain_type.name}",
            amount=instance.payable_by_buyer
        )
        return
    
    # Handle specific status transitions
    # NOTE: 'approved' status no longer creates invoice - handled by GRN signal
    if instance.status == 'allocated':
        _handle_trade_allocation(instance)
    elif instance.status == 'delivered':
        _handle_trade_delivery(instance)
    elif instance.status == 'completed':
        _handle_trade_completion(instance)
    elif instance.status == 'cancelled':
        _handle_trade_cancellation(instance)


def _handle_trade_allocation(trade):
    """Process when vouchers are allocated"""
    try:
        inventory = Inventory.objects.get(
            hub=trade.hub,
            grain_type=trade.grain_type
        )
        
        LedgerEntry.objects.create(
            event_type='inventory_reserved',
            related_object_id=trade.id,
            user=trade.initiated_by,
            hub=trade.hub,
            timestamp=timezone.now(),
            description=f"Inventory reserved for trade {trade.trade_number} - {trade.quantity_kg}kg",
            amount=Decimal('0.00')
        )
    except Inventory.DoesNotExist:
        pass


def _handle_trade_delivery(trade):
    """Process when goods are delivered"""
    LedgerEntry.objects.create(
        event_type='trade_delivered',
        related_object_id=trade.id,
        user=None,
        hub=trade.hub,
        timestamp=timezone.now(),
        description=f"Trade {trade.trade_number} delivered to {trade.buyer.name}",
        amount=trade.payable_by_buyer
    )
    
    # Update inventory - reduce total quantity
    try:
        inventory = Inventory.objects.get(
            hub=trade.hub,
            grain_type=trade.grain_type
        )
        inventory.total_quantity_kg -= trade.quantity_kg
        inventory.save()
        
        LedgerEntry.objects.create(
            event_type='inventory_dispatched',
            related_object_id=trade.id,
            user=None,
            hub=trade.hub,
            timestamp=timezone.now(),
            description=f"Inventory dispatched for trade {trade.trade_number}",
            amount=Decimal('0.00')
        )
    except Inventory.DoesNotExist:
        pass


def _handle_trade_completion(trade):
    """Process when trade is completed and payment received"""
    with transaction.atomic():
        LedgerEntry.objects.create(
            event_type='trade_completed',
            related_object_id=trade.id,
            user=None,
            hub=trade.hub,
            timestamp=timezone.now(),
            description=f"Trade {trade.trade_number} completed",
            amount=trade.payable_by_buyer
        )
        
        # Distribute profits to investors
        _distribute_trade_profits(trade)


def _distribute_trade_profits(trade):
    """Distribute profits to investors based on their allocations"""
    from investors.models import ProfitSharingAgreement
    
    if not trade.financing_allocations.exists():
        return
    
    for financing in trade.financing_allocations.all():
        investor_account = financing.investor_account
        
        # Get profit sharing agreement
        agreement = investor_account.profit_agreements.order_by('-effective_date').first()
        profit_threshold = agreement.profit_threshold if agreement else Decimal('2.00')
        investor_share = agreement.investor_share if agreement else Decimal('75.00')
        bennu_share = agreement.bennu_share if agreement else Decimal('25.00')
        
        # Calculate margin for this allocation
        margin_percentage = (trade.margin / trade.total_trade_cost * 100) if trade.total_trade_cost > 0 else Decimal('0.00')
        
        # Calculate this investor's share of the margin
        financing.margin_earned = (trade.margin * financing.allocated_amount / trade.total_trade_cost) if trade.total_trade_cost > 0 else Decimal('0.00')
        
        # Apply profit sharing rules
        if margin_percentage <= profit_threshold:
            financing.investor_margin = financing.margin_earned
            financing.bennu_margin = Decimal('0.00')
        else:
            financing.investor_margin = financing.margin_earned * investor_share / 100
            financing.bennu_margin = financing.margin_earned * bennu_share / 100
        
        financing.save()
        
        # Update investor account
        investor_account.release_from_trade(
            amount=financing.allocated_amount,
            profit=financing.investor_margin
        )
        
        # Create ledger entries
        LedgerEntry.objects.create(
            event_type='trade_profit',
            related_object_id=financing.id,
            user=investor_account.investor,
            hub=trade.hub,
            description=f"Profit from trade {trade.trade_number}: {financing.investor_margin} UGX",
            amount=financing.investor_margin
        )
        
        if financing.bennu_margin > 0:
            LedgerEntry.objects.create(
                event_type='bennu_profit',
                related_object_id=financing.id,
                user=None,
                hub=trade.hub,
                description=f"bennu share from trade {trade.trade_number}: {financing.bennu_margin} UGX",
                amount=financing.bennu_margin
            )


def _handle_trade_cancellation(trade):
    """Process when trade is cancelled"""
    # Deallocate vouchers if allocated
    if trade.allocation_complete:
        try:
            trade.deallocate_vouchers()
        except Exception as e:
            LedgerEntry.objects.create(
                event_type='trade_error',
                related_object_id=trade.id,
                user=None,
                hub=trade.hub,
                timestamp=timezone.now(),
                description=f"Error deallocating vouchers: {str(e)}",
                amount=Decimal('0.00')
            )
    
    # Release investor funds
    for financing in trade.financing_allocations.all():
        investor_account = financing.investor_account
        investor_account.total_utilized -= financing.allocated_amount
        investor_account.available_balance += financing.allocated_amount
        investor_account.save()
        
        LedgerEntry.objects.create(
            event_type='financing_released',
            related_object_id=financing.id,
            user=investor_account.investor,
            hub=trade.hub,
            description=f"Financing released due to trade cancellation: {financing.allocated_amount} UGX",
            amount=financing.allocated_amount
        )
    
    LedgerEntry.objects.create(
        event_type='trade_cancelled',
        related_object_id=trade.id,
        user=None,
        hub=trade.hub,
        timestamp=timezone.now(),
        description=f"Trade {trade.trade_number} cancelled",
        amount=Decimal('0.00')
    )


@receiver(post_save, sender=TradeFinancing)
def handle_trade_financing(sender, instance, created, **kwargs):
    """Handle investor capital allocation to trades"""
    if created:
        with transaction.atomic():
            # Deduct from investor's available balance
            investor_account = instance.investor_account
            investor_account.allocate_to_trade(instance.allocated_amount)
            
            # Create ledger entry
            LedgerEntry.objects.create(
                event_type='trade_allocation',
                related_object_id=instance.id,
                user=investor_account.investor,
                hub=instance.trade.hub,
                description=f"Allocated {instance.allocated_amount} UGX to trade {instance.trade.trade_number}",
                amount=-instance.allocated_amount
            )
            
            # Check if trade is fully financed
            trade = instance.trade
            if trade.requires_financing and trade.is_fully_financed():
                trade.financing_complete = True
                trade.status = 'pending_allocation'
                trade.save(update_fields=['financing_complete', 'status'])



@receiver(post_save, sender=TradeLoan)
def handle_trade_loan(sender, instance, created, **kwargs):
    """Handle investor loan disbursement"""
    if created:
        with transaction.atomic():
            # Deduct from investor's available balance
            investor_account = instance.investor_account
            investor_account.allocate_to_trade(instance.amount)
            
            # Create ledger entry
            LedgerEntry.objects.create(
                event_type='loan_disbursement',
                related_object_id=instance.id,
                user=investor_account.investor,
                hub=instance.trade.hub,
                description=f"Loan of {instance.amount} UGX for trade {instance.trade.trade_number}",
                amount=-instance.amount
            )


@receiver(post_save, sender=GoodsReceivedNote)
def handle_grn_creation(sender, instance, created, **kwargs):
    """Handle GRN creation"""
    if created:
        LedgerEntry.objects.create(
            event_type='grn_created',
            related_object_id=instance.id,
            user=None,
            hub=instance.trade.hub,
            timestamp=timezone.now(),
            description=f"GRN {instance.grn_number} created for trade {instance.trade.trade_number}",
            amount=Decimal('0.00')
        )