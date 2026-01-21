# vouchers/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from vouchers.models import Deposit, PriceFeed, Voucher, Redemption, PurchaseOffer, Inventory, LedgerEntry
from decimal import Decimal
from django.utils import timezone

@receiver(post_save, sender=Deposit)
def issue_voucher_on_deposit(sender, instance, created, **kwargs):
    """
    Issue voucher when deposit is created or validated.
    - Hub admin deposits: immediately verified
    - Agent deposits: pending verification
    """
    if created and not hasattr(instance, 'voucher'):
        entry_price = instance.calculate_value() / instance.quantity_kg if instance.quantity_kg > 0 else Decimal('0.00')
        
        # Determine verification status based on who made the deposit
        if instance.agent:
            # Agent deposit - needs hub admin verification
            verification_status = 'pending'
            voucher_status = 'pending_verification'
        else:
            # Hub admin deposit - immediately verified
            verification_status = 'verified'
            voucher_status = 'issued'
        
        voucher = Voucher.objects.create(
            deposit=instance,
            holder=instance.farmer,
            entry_price=entry_price,
            current_value=instance.calculate_value(),
            status=voucher_status,
            verification_status=verification_status,
            grn_number=instance.grn_number
        )
        
        # Only update inventory for verified deposits
        if verification_status == 'verified':
            update_inventory_on_deposit(instance)
        
        # Create ledger entry
        LedgerEntry.objects.create(
            event_type='deposit',
            related_object_id=instance.id,
            user=instance.farmer,
            hub=instance.hub,
            description=f"Deposit of {instance.quantity_kg}kg {instance.grain_type} {'by agent' if instance.agent else 'direct'}",
            amount=instance.calculate_value()
        )

def update_inventory_on_deposit(deposit_instance):
    """Helper function to update inventory when deposit is verified"""
    inv, created = Inventory.objects.get_or_create(
        hub=deposit_instance.hub, 
        grain_type=deposit_instance.grain_type,
        defaults={
            'total_quantity_kg': Decimal('0.00'),
            'available_quantity_kg': Decimal('0.00')
        }
    )
    inv.total_quantity_kg += deposit_instance.quantity_kg
    inv.available_quantity_kg += deposit_instance.quantity_kg
    inv.save()

@receiver(post_save, sender=Voucher)
def handle_voucher_verification(sender, instance, created, **kwargs):
    """Handle voucher verification status changes"""
    if not created and instance.verification_status == 'verified':
        # Check if this is a newly verified voucher (status change)
        if instance.status == 'pending_verification':
            instance.status = 'issued'
            instance.verified_at = timezone.now()
            instance.save(update_fields=['status', 'verified_at'])
            
            # Update inventory now that deposit is verified
            update_inventory_on_deposit(instance.deposit)
            
            # Create verification ledger entry
            LedgerEntry.objects.create(
                event_type='voucher_verified',
                related_object_id=instance.id,
                user=instance.verified_by,
                hub=instance.deposit.hub,
                description=f"Voucher verified for {instance.deposit.quantity_kg}kg {instance.deposit.grain_type}",
                amount=instance.current_value
            )

@receiver(post_save, sender=PurchaseOffer)
def transfer_voucher_on_accept(sender, instance, **kwargs):
    if instance.status == 'accepted':
        voucher = instance.voucher
        
        # Only allow transfer of verified vouchers
        if voucher.verification_status != 'verified':
            # This should be prevented by business logic, but just in case
            return
            
        voucher.holder = instance.investor
        voucher.status = 'transferred'
        voucher.save()
        
        # Ledger entry
        LedgerEntry.objects.create(
            event_type='voucher_transfer',
            related_object_id=voucher.id,
            user=instance.investor,
            hub=voucher.deposit.hub,
            description=f"Transfer to {instance.investor}",
            amount=instance.offer_price
        )

@receiver(post_save, sender=Redemption)
def process_redemption(sender, instance, **kwargs):
    if instance.status == 'approved' and instance.fee == Decimal('0.00'):
        voucher = instance.voucher
        
        # Only allow redemption of verified vouchers
        if voucher.verification_status != 'verified':
            return
            
        instance.calculate_fees_and_net()
        
        if instance.amount < voucher.current_value:
            # Partial redemption: Create new voucher for remainder
            remainder = voucher.current_value - instance.amount
            new_voucher = Voucher.objects.create(
                deposit=voucher.deposit,
                holder=voucher.holder,
                entry_price=voucher.entry_price,
                current_value=remainder,
                status='issued',
                verification_status='verified',  # Same verification status as parent
                verified_by=voucher.verified_by,
                verified_at=voucher.verified_at
            )
            voucher.current_value = instance.amount
        
        voucher.status = 'redeemed'
        voucher.save()
        
        # Update inventory
        inv = Inventory.objects.get(
            hub=voucher.deposit.hub, 
            grain_type=voucher.deposit.grain_type
        )
        redeemed_kg = instance.amount / voucher.entry_price
        inv.available_quantity_kg -= Decimal(str(redeemed_kg))
        inv.save()
        
        # Ledger entry
        LedgerEntry.objects.create(
            event_type='redemption',
            related_object_id=instance.id,
            user=instance.requester,
            hub=voucher.deposit.hub,
            description=f"Redemption of {instance.amount}, net {instance.net_payout}",
            amount=-instance.amount
        )

@receiver(post_save, sender=PriceFeed)
def update_vouchers_on_price_feed_change(sender, instance, **kwargs):
    """Update all vouchers for the grain type when a new price feed is created"""
    vouchers = Voucher.objects.filter(
        deposit__grain_type=instance.grain_type,
        deposit__hub=instance.hub or None,
        status__in=['issued', 'transferred']
    )
    for voucher in vouchers:
        voucher.update_value()