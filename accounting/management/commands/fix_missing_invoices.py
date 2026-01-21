# Save as: accounting/management/commands/fix_missing_invoices.py

from django.core.management.base import BaseCommand
from django.db import transaction
from trade.models import GoodsReceivedNote
from accounting.models import Invoice
import traceback


class Command(BaseCommand):
    help = 'Find GRNs without invoices and create them'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )
        parser.add_argument(
            '--grn-id',
            type=str,
            help='Process specific GRN by ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        grn_id = options.get('grn_id')
        
        self.stdout.write("=" * 60)
        self.stdout.write("FIXING MISSING INVOICES FOR GRNs")
        self.stdout.write("=" * 60)
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
        
        # Find GRNs without invoices
        if grn_id:
            grns = GoodsReceivedNote.objects.filter(id=grn_id)
            if not grns.exists():
                self.stdout.write(self.style.ERROR(f"GRN with ID {grn_id} not found"))
                return
        else:
            grns = GoodsReceivedNote.objects.filter(invoice__isnull=True).select_related('trade', 'trade__buyer')
        
        total = grns.count()
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS("No GRNs without invoices found!"))
            return
        
        self.stdout.write(f"Found {total} GRN(s) without invoices\n")
        
        created_count = 0
        failed_count = 0
        
        for grn in grns:
            self.stdout.write(f"\nProcessing GRN: {grn.grn_number}")
            self.stdout.write(f"  Trade: {grn.trade.trade_number}")
            self.stdout.write(f"  Buyer: {grn.trade.buyer.name}")
            self.stdout.write(f"  Quantity: {grn.net_weight_kg} kg")
            self.stdout.write(f"  Delivery Date: {grn.delivery_date}")
            
            if dry_run:
                self.stdout.write(self.style.WARNING("  [DRY RUN] Would create invoice"))
                created_count += 1
                continue
            
            try:
                with transaction.atomic():
                    # Check if invoice exists (in case of race condition)
                    if Invoice.objects.filter(grn=grn).exists():
                        self.stdout.write(self.style.WARNING("  Invoice already exists - skipping"))
                        continue
                    
                    # Create invoice
                    trade = grn.trade
                    invoice = Invoice(
                        grn=grn,
                        trade=trade,
                        account=trade.buyer,
                        issue_date=grn.delivery_date,
                        delivery_date=grn.delivery_date,
                        status='issued',
                        created_by=trade.approved_by
                    )
                    
                    # Populate from GRN
                    invoice.populate_from_grn()
                    invoice.save()
                    
                    self.stdout.write(self.style.SUCCESS(f"  ✅ Created invoice: {invoice.invoice_number}"))
                    self.stdout.write(f"     Amount: {invoice.total_amount} UGX")
                    
                    created_count += 1
                    
            except Exception as e:
                failed_count += 1
                self.stdout.write(self.style.ERROR(f"  ❌ Failed: {str(e)}"))
                self.stdout.write(traceback.format_exc())
        
        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("SUMMARY")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Total GRNs processed: {total}")
        self.stdout.write(self.style.SUCCESS(f"Invoices created: {created_count}"))
        
        if failed_count > 0:
            self.stdout.write(self.style.ERROR(f"Failed: {failed_count}"))
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\nThis was a DRY RUN - no changes were made"))
            self.stdout.write("Run without --dry-run to actually create invoices")