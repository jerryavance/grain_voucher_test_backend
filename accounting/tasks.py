# accounting/tasks.py
from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from .models import Invoice, InvoiceLineItem, JournalEntry
from trade.models import GoodsReceivedNote
from django.db.models import Sum, Q
from datetime import date, timedelta, datetime


@shared_task
def generate_scheduled_invoices():
    """
    Celery task to generate consolidated invoices that are scheduled.
    Should run multiple times daily (e.g., every 2-4 hours).
    
    This finalizes draft invoices whose scheduled_generation_date has passed.
    """
    now = timezone.now()
    
    # Get all draft invoices scheduled for generation that are past due
    scheduled_invoices = Invoice.objects.filter(
        status='draft',
        is_auto_generated=True,
        scheduled_generation_date__lte=now
    )
    
    generated_count = 0
    
    for invoice in scheduled_invoices:
        try:
            # Check if invoice has line items
            if not invoice.line_items.exists():
                # No deliveries in this period, delete the draft
                invoice.delete()
                continue
            
            # Finalize the invoice
            invoice.status = 'issued'
            invoice.issue_date = timezone.now().date()
            invoice.scheduled_generation_date = None
            
            # Recalculate amounts one final time
            invoice.calculate_amounts()
            invoice.save()
            
            # Create journal entry for the consolidated invoice
            JournalEntry.objects.create(
                entry_type='sale',
                entry_date=invoice.issue_date,
                debit_account='Accounts Receivable',
                credit_account='Sales Revenue',
                amount=invoice.total_amount,
                related_invoice=invoice,
                description=f"Consolidated invoice {invoice.invoice_number} for period {invoice.period_start} to {invoice.period_end}",
                notes=f"Buyer: {invoice.account.name}, {invoice.line_items.count()} deliveries"
            )
            
            generated_count += 1
            
            # Optionally send invoice email
            send_invoice_email.delay(str(invoice.id))
            
        except Exception as e:
            print(f"Error generating invoice {invoice.id}: {str(e)}")
            continue
    
    print(f"Generated {generated_count} scheduled invoices")
    return generated_count


@shared_task
def check_overdue_invoices():
    """
    Celery task to check and update overdue invoices.
    Run this daily via cron or beat scheduler.
    """
    today = timezone.now().date()
    overdue_invoices = Invoice.objects.filter(
        status__in=['sent', 'issued', 'partially_paid'],
        due_date__lt=today,
        payment_status__in=['unpaid', 'partial']
    )
    
    updated_count = 0
    for invoice in overdue_invoices:
        old_status = invoice.payment_status
        invoice.update_payment_status()
        if invoice.payment_status != old_status:
            invoice.save()
            updated_count += 1
    
    print(f"Updated {updated_count} overdue invoices")
    return updated_count


@shared_task
def send_invoice_email(invoice_id):
    """
    Celery task to send invoice email.
    Integrate with email backend.
    """
    from .models import Invoice
    try:
        invoice = Invoice.objects.get(id=invoice_id)
        
        # TODO: Implement email sending logic
        # Example structure:
        # subject = f"Invoice {invoice.invoice_number} from bennu"
        # html_content = render_to_string('emails/invoice.html', {'invoice': invoice})
        # send_mail(subject, '', 'noreply@bennu.com', [invoice.account.email], html_message=html_content)
        
        # Update invoice
        if invoice.status == 'issued':
            invoice.status = 'sent'
            invoice.sent_date = timezone.now()
            invoice.save()
        
        print(f"Email sent for invoice {invoice.invoice_number}")
        return True
    except Invoice.DoesNotExist:
        print(f"Invoice {invoice_id} not found")
        return False


@shared_task
def send_payment_reminder(invoice_id):
    """
    Celery task to send payment reminder.
    Integrate with email/SMS backend.
    """
    from .models import Invoice
    try:
        invoice = Invoice.objects.get(id=invoice_id)
        
        # TODO: Implement reminder sending logic
        # subject = f"Payment Reminder: Invoice {invoice.invoice_number}"
        # html_content = render_to_string('emails/payment_reminder.html', {'invoice': invoice})
        # send_mail(subject, '', 'noreply@bennu.com', [invoice.account.email], html_message=html_content)
        
        print(f"Reminder sent for overdue invoice {invoice.invoice_number}")
        return True
    except Invoice.DoesNotExist:
        print(f"Invoice {invoice_id} not found")
        return False


@shared_task
def auto_send_reminders_for_overdue():
    """
    Automatically send reminders for overdue invoices.
    Run daily.
    """
    from .models import Invoice
    today = timezone.now()
    
    # Get overdue invoices that haven't had a reminder in the last 7 days
    overdue_invoices = Invoice.objects.filter(
        status='overdue',
        payment_status__in=['unpaid', 'partial']
    ).filter(
        Q(last_reminder_sent__isnull=True) |
        Q(last_reminder_sent__lt=today - timedelta(days=7))
    )
    
    sent_count = 0
    for invoice in overdue_invoices:
        send_payment_reminder.delay(str(invoice.id))
        sent_count += 1
    
    print(f"Sent {sent_count} payment reminders")
    return sent_count


@shared_task
def consolidate_pending_grns():
    """
    Manual task to consolidate pending GRNs into invoices.
    Can be triggered by admin or run on schedule.
    """
    from trade.models import GoodsReceivedNote
    
    # Get GRNs that don't have invoice line items yet
    pending_grns = GoodsReceivedNote.objects.filter(
        invoice_items__isnull=True,
        trade__status__in=['delivered', 'approved']
    ).select_related('trade', 'trade__buyer')
    
    processed = 0
    for grn in pending_grns:
        try:
            # Determine invoicing frequency and create/update invoice
            trade = grn.trade
            payment_terms_days = trade.payment_terms_days
            invoicing_frequency = Invoice.determine_invoicing_frequency(payment_terms_days)
            
            if invoicing_frequency == 'immediate':
                from .signals import _create_immediate_invoice
                _create_immediate_invoice(grn, trade)
            else:
                from .signals import _add_to_consolidated_invoice
                _add_to_consolidated_invoice(grn, trade, invoicing_frequency)
            
            processed += 1
        except Exception as e:
            print(f"Error processing GRN {grn.grn_number}: {str(e)}")
            continue
    
    print(f"Processed {processed} pending GRNs")
    return processed


# Setup Celery Beat schedule in your celery.py or settings.py:
"""
from celery.schedules import crontab

app.conf.beat_schedule = {
    'generate-scheduled-invoices': {
        'task': 'accounting.tasks.generate_scheduled_invoices',
        'schedule': crontab(hour='*/4'),  # Every 4 hours
    },
    'check-overdue-invoices': {
        'task': 'accounting.tasks.check_overdue_invoices',
        'schedule': crontab(hour=1, minute=0),  # Daily at 1 AM
    },
    'send-payment-reminders': {
        'task': 'accounting.tasks.auto_send_reminders_for_overdue',
        'schedule': crontab(hour=9, minute=0),  # Daily at 9 AM
    },
}
"""