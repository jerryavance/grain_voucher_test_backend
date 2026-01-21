# crm/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Contract
from trade.models import Trade  # Import to create Trade on execution
from vouchers.models import GrainType  # Assume default grain_type
from hubs.models import Hub

@receiver(post_save, sender=Contract)
def create_trade_on_execution(sender, instance, **kwargs):
    if instance.status == 'executed' and instance.opportunity.stage == 'won':
        # Create Trade from Opportunity
        Trade.objects.create(
            buyer=instance.opportunity.account,
            grain_type=GrainType.objects.first(),  # Placeholder; refine based on opp
            quantity_mt=instance.opportunity.expected_volume_mt,
            price_per_mt=instance.opportunity.expected_price_per_mt,
            grade='default',  # Add grade to Opportunity if needed
            initiated_by=instance.opportunity.assigned_to,
            hub=instance.opportunity.account.hub or Hub.objects.first(),  # Fallback
        )