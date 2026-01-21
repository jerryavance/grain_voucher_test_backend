# reports/tasks.py - FIXED VERSION
from celery import shared_task
from django.core.mail import EmailMessage
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import logging
import os

from .models import ReportExport, ReportSchedule
from .utils import (
    generate_report_data,
    export_to_csv,
    export_to_excel,
    export_to_pdf,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def generate_report_async(self, report_export_id):
    """
    Generate a report asynchronously
    """
    try:
        report_export = ReportExport.objects.get(id=report_export_id)
        report_export.status = 'processing'
        report_export.save()
        
        # Generate report data
        data = generate_report_data(report_export.report_type, report_export.filters)
        
        # Prepare data based on report type
        export_data, columns = prepare_report_for_export(report_export.report_type, data)
        
        # Generate file
        file_content = generate_file_content(
            export_data,
            columns,
            report_export.format,
            report_export.report_type
        )
        
        # Save file
        file_path = save_report_file(report_export, file_content)
        
        # Mark as completed
        report_export.mark_completed(file_path, len(export_data))
        
        logger.info(f"Report {report_export_id} generated successfully")
        return str(report_export_id)
        
    except Exception as e:
        logger.error(f"Failed to generate report {report_export_id}: {str(e)}")
        
        try:
            report_export = ReportExport.objects.get(id=report_export_id)
            report_export.mark_failed(str(e))
        except:
            pass
        
        # Retry
        raise self.retry(exc=e, countdown=60)


@shared_task
def run_scheduled_reports():
    """
    Run scheduled reports that are due
    """
    now = timezone.now()
    
    # Get active schedules that are due
    schedules = ReportSchedule.objects.filter(
        is_active=True,
        next_run__lte=now
    )
    
    for schedule in schedules:
        try:
            # Create report export
            report_export = ReportExport.objects.create(
                report_type=schedule.report_type,
                format=schedule.format,
                filters=schedule.filters,
                generated_by=schedule.created_by,
                hub=schedule.hub,
                status='pending'
            )
            
            # Generate report asynchronously
            generate_report_async.delay(str(report_export.id))
            
            # Update schedule
            schedule.last_run = now
            schedule.next_run = calculate_next_run(schedule)
            schedule.save()
            
            # Send to recipients once generated
            send_scheduled_report_to_recipients.delay(
                str(report_export.id),
                list(schedule.recipients.values_list('id', flat=True))
            )
            
            logger.info(f"Scheduled report {schedule.id} triggered")
            
        except Exception as e:
            logger.error(f"Failed to run scheduled report {schedule.id}: {str(e)}")


@shared_task
def send_scheduled_report_to_recipients(report_export_id, recipient_ids):
    """
    Send scheduled report to recipients via email
    """
    try:
        report_export = ReportExport.objects.get(id=report_export_id)
        
        # Wait for report to be completed (with timeout)
        max_attempts = 30
        attempts = 0
        
        while report_export.status != 'completed' and attempts < max_attempts:
            import time
            time.sleep(10)  # Wait 10 seconds
            report_export.refresh_from_db()
            attempts += 1
        
        if report_export.status != 'completed':
            logger.error(f"Report {report_export_id} not completed after waiting")
            return
        
        # Get recipients
        from authentication.models import GrainUser
        recipients = GrainUser.objects.filter(id__in=recipient_ids, email__isnull=False)
        
        if not recipients.exists():
            logger.warning(f"No recipients with email found for report {report_export_id}")
            return
        
        # Send email
        subject = f"Scheduled Report: {report_export.get_report_type_display()}"
        body = f"""
        Hello,
        
        Your scheduled report "{report_export.get_report_type_display()}" has been generated.
        
        Report Details:
        - Type: {report_export.get_report_type_display()}
        - Format: {report_export.get_format_display()}
        - Records: {report_export.record_count}
        - Generated: {report_export.completed_at.strftime('%Y-%m-%d %H:%M')}
        
        Please find the report attached.
        
        Best regards,
        Grain Management System
        """
        
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient.email for recipient in recipients if recipient.email],
        )
        
        # Attach file
        if report_export.file_path and os.path.exists(report_export.file_path):
            filename = f"{report_export.report_type}_report.{report_export.format}"
            with open(report_export.file_path, 'rb') as f:
                email.attach(filename, f.read(), get_content_type(report_export.format))
        
        email.send()
        
        logger.info(f"Report {report_export_id} sent to {len(recipients)} recipients")
        
    except Exception as e:
        logger.error(f"Failed to send report {report_export_id}: {str(e)}")


@shared_task
def cleanup_expired_reports():
    """
    Cleanup expired report files
    """
    expired_reports = ReportExport.objects.filter(
        expires_at__lt=timezone.now()
    )
    
    count = 0
    for report in expired_reports:
        try:
            if report.file_path and os.path.exists(report.file_path):
                os.remove(report.file_path)
            report.delete()
            count += 1
        except Exception as e:
            logger.error(f"Failed to cleanup report {report.id}: {str(e)}")
    
    logger.info(f"Cleaned up {count} expired reports")
    return count


def prepare_report_for_export(report_type, data):
    """
    Prepare report data and columns based on report type
    """
    try:
        if report_type == 'supplier':
            columns = ['supplier_name', 'phone_number', 'total_trades', 'total_quantity_kg', 'total_value', 'avg_price_per_kg']
            export_data = [
                {
                    'supplier_name': f"{row['supplier__first_name']} {row['supplier__last_name']}",
                    'phone_number': row.get('supplier__phone_number', 'N/A'),
                    'total_trades': row['total_trades'],
                    'total_quantity_kg': row['total_quantity_kg'],
                    'total_value': row['total_value'],
                    'avg_price_per_kg': row['avg_price_per_kg'],
                }
                for row in data
            ]
        
        # elif report_type == 'trade':
        #     columns = [
        #         'trade_number', 'buyer', 'supplier', 'grain_type', 'quantity_kg',
        #         'total_trade_cost', 'status', 'created_at'
        #     ]
        #     export_data = [
        #         {
        #             'trade_number': trade.trade_number,
        #             'buyer': trade.buyer.name,  # FIXED
        #             'supplier': f"{trade.supplier.first_name} {trade.supplier.last_name}".strip() or trade.supplier.phone_number,
        #             'grain_type': trade.grain_type.name,
        #             'quantity_kg': float(trade.quantity_kg),
        #             'total_trade_cost': float(trade.total_trade_cost),
        #             'status': trade.get_status_display(),
        #             'created_at': trade.created_at.strftime('%Y-%m-%d'),
        #         }
        #         for trade in data
        #     ]

        elif report_type == 'trade':
            columns = [
                'trade_number', 'date', 'buyer', 'supplier', 'grain_type', 
                'quantity_kg', 'buying_price', 'selling_price', 
                'total_trade_cost', 'payable_by_buyer', 'margin', 'status'
            ]
            export_data = []
            
            for trade in data:
                # ✅ Use 'name' field (confirmed working)
                buyer_name = trade.buyer.name if trade.buyer else 'N/A'
                
                # ✅ Build supplier name
                supplier_name = 'N/A'
                if trade.supplier:
                    supplier_name = f"{trade.supplier.first_name} {trade.supplier.last_name}".strip()
                    if not supplier_name:
                        supplier_name = trade.supplier.phone_number or 'Unknown'
                
                export_data.append({
                    'trade_number': trade.trade_number,
                    'date': trade.created_at.strftime('%Y-%m-%d'),
                    'buyer': buyer_name,
                    'supplier': supplier_name,
                    'grain_type': trade.grain_type.name if trade.grain_type else 'N/A',
                    'quantity_kg': float(trade.quantity_kg),
                    'buying_price': float(trade.buying_price),
                    'selling_price': float(trade.selling_price),
                    'total_trade_cost': float(trade.total_trade_cost),
                    'payable_by_buyer': float(trade.payable_by_buyer),
                    'margin': float(trade.margin),
                    'status': trade.get_status_display(),
                })
            
            return export_data, columns
        
        elif report_type == 'invoice':
            columns = ['invoice_number', 'issue_date', 'due_date', 'account', 'total_amount', 'amount_paid', 'amount_due', 'payment_status']
            export_data = [
                {
                    'invoice_number': invoice.invoice_number,
                    'issue_date': invoice.issue_date.strftime('%Y-%m-%d'),
                    'due_date': invoice.due_date.strftime('%Y-%m-%d'),
                    'account': invoice.account.account_name,
                    'total_amount': float(invoice.total_amount),
                    'amount_paid': float(invoice.amount_paid),
                    'amount_due': float(invoice.amount_due),
                    'payment_status': invoice.payment_status,
                }
                for invoice in data
            ]
        
        elif report_type == 'payment':
            columns = ['payment_date', 'invoice_number', 'account', 'amount', 'payment_method', 'reference_number', 'created_by']
            export_data = [
                {
                    'payment_date': payment.payment_date.strftime('%Y-%m-%d'),
                    'invoice_number': payment.invoice.invoice_number,
                    'account': payment.invoice.account.account_name,
                    'amount': float(payment.amount),
                    'payment_method': payment.payment_method,
                    'reference_number': payment.reference_number or 'N/A',
                    'created_by': payment.created_by.phone_number if payment.created_by else 'N/A',
                }
                for payment in data
            ]
        
        elif report_type == 'depositor':
            # ✅ FIX: Use 'name' instead of 'grade'
            columns = ['farmer_name', 'phone_number', 'deposit_date', 'grain_type', 'quantity_kg', 'quality_grade', 'hub', 'validated']
            export_data = [
                {
                    'farmer_name': f"{deposit.farmer.first_name} {deposit.farmer.last_name}",
                    'phone_number': deposit.farmer.phone_number,
                    'deposit_date': deposit.deposit_date.strftime('%Y-%m-%d'),
                    'grain_type': deposit.grain_type.name,
                    'quantity_kg': float(deposit.quantity_kg),
                    'quality_grade': deposit.quality_grade.name if deposit.quality_grade else 'N/A',  # ✅ FIXED
                    'hub': deposit.hub.name,
                    'validated': 'Yes' if deposit.validated else 'No',
                }
                for deposit in data
            ]
        
        elif report_type == 'voucher':
            columns = ['voucher_id', 'issue_date', 'farmer', 'grain_type', 'quantity_kg', 'holder', 'status', 'verification_status']
            export_data = [
                {
                    'voucher_id': str(voucher.id)[:8],
                    'issue_date': voucher.issue_date.strftime('%Y-%m-%d'),
                    'farmer': f"{voucher.deposit.farmer.first_name} {voucher.deposit.farmer.last_name}",
                    'grain_type': voucher.deposit.grain_type.name,
                    'quantity_kg': float(voucher.deposit.quantity_kg),
                    'holder': voucher.holder.phone_number if voucher.holder else 'N/A',
                    'status': voucher.status,
                    'verification_status': voucher.verification_status,
                }
                for voucher in data
            ]
        
        elif report_type == 'inventory':
            columns = ['hub', 'grain_type', 'total_quantity_kg', 'available_quantity_kg']
            export_data = [
                {
                    'hub': inventory.hub.name,
                    'grain_type': inventory.grain_type.name,
                    'total_quantity_kg': float(inventory.total_quantity_kg),
                    'available_quantity_kg': float(inventory.available_quantity_kg),
                }
                for inventory in data
            ]
        
        elif report_type == 'investor':
            # ✅ FIX: Remove account_number field
            columns = ['investor_name', 'phone_number', 'total_deposited', 'total_utilized', 'available_balance', 'total_returns']
            export_data = [
                {
                    'investor_name': f"{account.investor.first_name} {account.investor.last_name}",
                    'phone_number': account.investor.phone_number,
                    'total_deposited': float(account.total_deposited),
                    'total_utilized': float(account.total_utilized),
                    'available_balance': float(account.available_balance),
                    'total_returns': float(account.total_margin_earned + account.total_interest_earned),
                }
                for account in data
            ]
        
        else:
            raise ValueError(f"Unknown report type: {report_type}")
        
        return export_data, columns
        
    except Exception as e:
        logger.error(f"Error in prepare_report_for_export for {report_type}: {str(e)}", exc_info=True)
        raise


def generate_file_content(data, columns, file_format, report_type):
    """
    Generate file content based on format
    """
    title = f"{report_type.replace('_', ' ').title()} Report"
    
    if file_format == 'csv':
        return export_to_csv(data, columns)
    elif file_format == 'excel':
        return export_to_excel(data, columns, title)
    elif file_format == 'pdf':
        return export_to_pdf(data, columns, title)
    else:
        raise ValueError(f"Unsupported format: {file_format}")


def save_report_file(report_export, file_content):
    """
    Save report file to disk
    """
    # Create reports directory
    reports_dir = os.path.join(settings.MEDIA_ROOT, 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    
    # Generate filename
    filename = f"{report_export.id}.{report_export.format}"
    file_path = os.path.join(reports_dir, filename)
    
    # Write file
    mode = 'wb' if isinstance(file_content, bytes) else 'w'
    with open(file_path, mode) as f:
        f.write(file_content)
    
    # Store file size
    report_export.file_size = os.path.getsize(file_path)
    report_export.save()
    
    return file_path


def calculate_next_run(schedule):
    """
    Calculate next run time for a schedule
    """
    from datetime import datetime, time
    
    now = timezone.now()
    
    if schedule.frequency == 'daily':
        next_run = now + timedelta(days=1)
    
    elif schedule.frequency == 'weekly':
        # Find next occurrence of day_of_week
        days_ahead = schedule.day_of_week - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_run = now + timedelta(days=days_ahead)
    
    elif schedule.frequency == 'monthly':
        # Find next occurrence of day_of_month
        next_run = now.replace(day=schedule.day_of_month)
        if next_run <= now:
            # Move to next month
            if next_run.month == 12:
                next_run = next_run.replace(year=next_run.year + 1, month=1)
            else:
                next_run = next_run.replace(month=next_run.month + 1)
    
    elif schedule.frequency == 'quarterly':
        # Move 3 months ahead
        next_run = now + timedelta(days=90)
    
    else:
        next_run = now + timedelta(days=1)
    
    # Set the time
    next_run = next_run.replace(
        hour=schedule.time_of_day.hour,
        minute=schedule.time_of_day.minute,
        second=0,
        microsecond=0
    )
    
    return next_run


def get_content_type(file_format):
    """
    Get content type for file format
    """
    content_types = {
        'pdf': 'application/pdf',
        'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'csv': 'text/csv',
    }
    return content_types.get(file_format, 'application/octet-stream')