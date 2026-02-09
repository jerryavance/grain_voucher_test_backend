# sourcing/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

from .models import (
    SourceOrder, SupplierInvoice, DeliveryRecord, 
    WeighbridgeRecord, SupplierPayment, Notification
)
from vouchers.models import LedgerEntry


@receiver(post_save, sender=SourceOrder)
def handle_source_order_status_changes(sender, instance, created, **kwargs):
    """Handle automatic processes when source order status changes"""
    
    if created:
        # Create initial ledger entry
        LedgerEntry.objects.create(
            event_type='source_order_created',
            related_object_id=instance.id,
            user=instance.created_by,
            hub=instance.hub,
            timestamp=timezone.now(),
            description=f"Source order {instance.order_number} created for {instance.supplier.business_name} - {instance.quantity_kg}kg {instance.grain_type.name}",
            amount=instance.total_cost
        )
        return
    
    # Handle status transitions
    if instance.status == 'accepted':
        _handle_order_acceptance(instance)
    elif instance.status == 'completed':
        _handle_order_completion(instance)
    elif instance.status == 'cancelled':
        _handle_order_cancellation(instance)


def _handle_order_acceptance(order):
    """Process when supplier accepts order"""
    # Create supplier invoice automatically
    try:
        # Check if invoice already exists
        if hasattr(order, 'supplier_invoice'):
            return
        
        # Calculate due date (e.g., 7 days after acceptance)
        due_date = (order.accepted_at + timedelta(days=7)).date() if order.accepted_at else None
        
        # Create invoice
        invoice = SupplierInvoice.objects.create(
            source_order=order,
            supplier=order.supplier,
            amount_due=order.grain_cost,  # Only grain cost, not other costs
            balance_due=order.grain_cost,
            payment_method=order.payment_method,
            status='pending',
            due_date=due_date
        )
        
        # Create notification for supplier
        Notification.objects.create(
            user=order.supplier.user,
            notification_type='invoice_generated',
            title="Invoice Generated",
            message=f"Invoice {invoice.invoice_number} has been generated for your order {order.order_number}. Amount: {invoice.amount_due} UGX",
            related_object_type='supplier_invoice',
            related_object_id=invoice.id
        )
        
        # Create ledger entry
        LedgerEntry.objects.create(
            event_type='supplier_invoice_created',
            related_object_id=invoice.id,
            user=order.supplier.user,
            hub=order.hub,
            timestamp=timezone.now(),
            description=f"Supplier invoice {invoice.invoice_number} created for order {order.order_number}",
            amount=invoice.amount_due
        )
        
    except Exception as e:
        print(f"Error creating supplier invoice for order {order.order_number}: {str(e)}")


def _handle_order_completion(order):
    """Process when order is completed (weighbridge record created)"""
    LedgerEntry.objects.create(
        event_type='source_order_completed',
        related_object_id=order.id,
        user=None,
        hub=order.hub,
        timestamp=timezone.now(),
        description=f"Source order {order.order_number} completed - grain added to inventory",
        amount=order.total_cost
    )
    
    # Notify supplier
    Notification.objects.create(
        user=order.supplier.user,
        notification_type='source_order_status',
        title="Order Completed",
        message=f"Your order {order.order_number} has been completed. Quality inspection passed.",
        related_object_type='source_order',
        related_object_id=order.id
    )


def _handle_order_cancellation(order):
    """Process when order is cancelled"""
    # Cancel related invoice if exists
    if hasattr(order, 'supplier_invoice'):
        invoice = order.supplier_invoice
        invoice.status = 'cancelled'
        invoice.save(update_fields=['status'])
    
    # Create ledger entry
    LedgerEntry.objects.create(
        event_type='source_order_cancelled',
        related_object_id=order.id,
        user=None,
        hub=order.hub,
        timestamp=timezone.now(),
        description=f"Source order {order.order_number} cancelled",
        amount=Decimal('0.00')
    )
    
    # Notify supplier
    Notification.objects.create(
        user=order.supplier.user,
        notification_type='source_order_status',
        title="Order Cancelled",
        message=f"Order {order.order_number} has been cancelled.",
        related_object_type='source_order',
        related_object_id=order.id
    )


@receiver(post_save, sender=DeliveryRecord)
def handle_delivery_creation(sender, instance, created, **kwargs):
    """Handle delivery record creation"""
    if not created:
        return
    
    # Update source order status
    order = instance.source_order
    if order.status == 'in_transit':
        order.status = 'delivered'
        order.delivered_at = instance.received_at
        order.save(update_fields=['status', 'delivered_at'])
    
    # Create ledger entry
    LedgerEntry.objects.create(
        event_type='delivery_received',
        related_object_id=instance.id,
        user=instance.received_by,
        hub=instance.hub,
        timestamp=instance.received_at,
        description=f"Delivery received for order {order.order_number} at {instance.hub.name}",
        amount=Decimal('0.00')
    )
    
    # Notify relevant parties
    Notification.objects.create(
        user=order.supplier.user,
        notification_type='delivery_received',
        title="Delivery Received",
        message=f"Your delivery for order {order.order_number} has been received at {instance.hub.name}",
        related_object_type='delivery_record',
        related_object_id=instance.id
    )


@receiver(post_save, sender=WeighbridgeRecord)
def handle_weighbridge_completion(sender, instance, created, **kwargs):
    """Handle weighbridge record completion"""
    if not created:
        return
    
    order = instance.source_order
    
    # Create ledger entry
    LedgerEntry.objects.create(
        event_type='weighbridge_completed',
        related_object_id=instance.id,
        user=instance.weighed_by,
        hub=order.hub,
        timestamp=instance.weighed_at,
        description=f"Weighbridge completed for order {order.order_number} - Net: {instance.net_weight_kg}kg, Variance: {instance.quantity_variance_kg}kg",
        amount=Decimal('0.00')
    )
    
    # Notify supplier
    Notification.objects.create(
        user=order.supplier.user,
        notification_type='weighbridge_completed',
        title="Quality Check Complete",
        message=f"Quality inspection completed for order {order.order_number}. Net weight: {instance.net_weight_kg}kg, Grade: {instance.quality_grade.name}",
        related_object_type='weighbridge_record',
        related_object_id=instance.id
    )


@receiver(post_save, sender=SupplierPayment)
def handle_supplier_payment(sender, instance, created, **kwargs):
    """Handle supplier payment processing"""
    if not created:
        return
    
    # If payment is completed, update invoice
    if instance.status == 'completed':
        with transaction.atomic():
            invoice = instance.supplier_invoice
            invoice.amount_paid += instance.amount
            invoice.update_payment_status()
            
            # Set payment reference on invoice
            if instance.reference_number and not invoice.payment_reference:
                invoice.payment_reference = instance.reference_number
                invoice.save(update_fields=['payment_reference'])
            
            # Create ledger entry
            LedgerEntry.objects.create(
                event_type='supplier_payment',
                related_object_id=instance.id,
                user=instance.processed_by,
                hub=instance.source_order.hub,
                timestamp=instance.completed_at or timezone.now(),
                description=f"Payment {instance.payment_number} made to supplier {invoice.supplier.business_name} - {instance.amount} UGX",
                amount=-instance.amount  # Negative because it's an outgoing payment
            )
            
            # Notify supplier
            Notification.objects.create(
                user=invoice.supplier.user,
                notification_type='payment_proof',
                title="Payment Processed",
                message=f"Payment of {instance.amount} UGX has been processed. Reference: {instance.reference_number or 'N/A'}",
                related_object_type='supplier_payment',
                related_object_id=instance.id
            )


@receiver(post_save, sender=SupplierInvoice)
def handle_invoice_paid(sender, instance, **kwargs):
    """Handle when invoice is fully paid"""
    if instance.status == 'paid' and not instance.paid_at:
        instance.paid_at = timezone.now()
        instance.save(update_fields=['paid_at'])
        
        # Notify supplier
        Notification.objects.create(
            user=instance.supplier.user,
            notification_type='payment_made',
            title="Invoice Fully Paid",
            message=f"Invoice {instance.invoice_number} has been fully paid. Total: {instance.amount_due} UGX",
            related_object_type='supplier_invoice',
            related_object_id=instance.id
        )