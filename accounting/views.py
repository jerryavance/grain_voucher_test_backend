# accounting/views.py - INVOICE BATCHING FOR SENDING
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Q, Count
from datetime import timedelta, date
from django.utils import timezone
from decimal import Decimal
from django.db import transaction

from trade.models import GoodsReceivedNote
from .models import Budget, Invoice, JournalEntry, Payment, InvoiceBatch
from .serializers import (
    InvoiceSerializer, InvoiceListSerializer,
    PaymentSerializer, InvoiceBatchSerializer
)
from utils.permissions import IsSuperAdmin, IsFinance
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .serializers import JournalEntrySerializer, BudgetSerializer


class InvoiceViewSet(ModelViewSet):
    """
    Invoice management with batch sending support.
    Invoices are created automatically per GRN.
    Batching happens only when sending to buyer.
    """
    queryset = Invoice.objects.select_related('account', 'grn', 'trade', 'created_by').prefetch_related('payments')
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'payment_status', 'account', 'trade']
    search_fields = ['invoice_number', 'account__name', 'grn__grn_number']
    ordering_fields = ['issue_date', 'due_date', 'total_amount', 'amount_due']
    ordering = ['-issue_date']

    def get_serializer_class(self):
        if self.action == 'list':
            return InvoiceListSerializer
        return InvoiceSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        qs = super().get_queryset()
        
        # Super admin and finance see all
        if user.role in ['super_admin', 'finance']:
            return qs
        
        # BDMs see invoices for trades they initiated
        elif user.role == 'bdm':
            return qs.filter(trade__initiated_by=user)
        
        # Clients see their own invoices
        elif user.role == 'client':
            account_ids = user.contact_accounts.values_list('account_id', flat=True)
            return qs.filter(account__in=account_ids)
        
        return qs.none()

    # ✅ NEW: Get unsent invoices for a buyer
    @action(detail=False, methods=['get'])
    def unsent_by_account(self, request):
        """
        Get all issued but unsent invoices for a specific buyer.
        These can be batched together for sending.
        """
        account_id = request.query_params.get('account_id')
        
        if not account_id:
            return Response(
                {"error": "account_id parameter required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get invoices that are issued but not yet sent in a batch
        unsent_invoices = self.get_queryset().filter(
            account_id=account_id,
            status='issued',
            batch_sent_date__isnull=True
        ).order_by('delivery_date')
        
        # Calculate summary
        summary = unsent_invoices.aggregate(
            count=Count('id'),
            total_amount=Sum('total_amount'),
            earliest_date=models.Min('delivery_date'),
            latest_date=models.Max('delivery_date')
        )
        
        serializer = InvoiceListSerializer(unsent_invoices, many=True)
        
        return Response({
            'summary': {
                'count': summary['count'] or 0,
                'total_amount': float(summary['total_amount'] or 0),
                'period_start': summary['earliest_date'].isoformat() if summary['earliest_date'] else None,
                'period_end': summary['latest_date'].isoformat() if summary['latest_date'] else None
            },
            'invoices': serializer.data
        })

    # ✅ NEW: Create and send invoice batch
    @action(detail=False, methods=['post'])
    def create_and_send_batch(self, request):
        """
        Create a batch from selected invoices and mark them as sent.
        This is how we "batch" invoices - only when sending to buyer.
        """
        if request.user.role not in ['super_admin', 'finance']:
            return Response(
                {"error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        invoice_ids = request.data.get('invoice_ids', [])
        send_email = request.data.get('send_email', True)
        notes = request.data.get('notes', '')
        
        if not invoice_ids:
            return Response(
                {"error": "invoice_ids required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Get invoices
                invoices = Invoice.objects.filter(
                    id__in=invoice_ids,
                    status='issued',
                    batch_sent_date__isnull=True
                ).select_related('account')
                
                if not invoices.exists():
                    return Response(
                        {"error": "No valid unsent invoices found"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Verify all invoices are for same account
                accounts = set(inv.account_id for inv in invoices)
                if len(accounts) > 1:
                    return Response(
                        {"error": "All invoices must be for the same buyer"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                account = invoices.first().account
                
                # Get date range
                delivery_dates = [inv.delivery_date for inv in invoices]
                period_start = min(delivery_dates)
                period_end = max(delivery_dates)
                
                # Create batch
                batch = InvoiceBatch.objects.create(
                    account=account,
                    period_start=period_start,
                    period_end=period_end,
                    invoice_count=invoices.count(),
                    total_amount=sum(inv.total_amount for inv in invoices),
                    notes=notes,
                    created_by=request.user
                )
                
                # Update invoices
                batch_sent_date = timezone.now()
                for invoice in invoices:
                    invoice.batch_id = batch.batch_number
                    invoice.batch_sent_date = batch_sent_date
                    invoice.status = 'sent'
                    invoice.save(update_fields=['batch_id', 'batch_sent_date', 'status'])
                
                # Send email if requested
                if send_email:
                    from .tasks import send_invoice_batch_email
                    send_invoice_batch_email.delay(str(batch.id))
                    batch.sent_via_email = True
                    batch.email_sent_date = batch_sent_date
                    batch.save()
                
                return Response({
                    "message": f"Batch created with {batch.invoice_count} invoices",
                    "batch": InvoiceBatchSerializer(batch).data
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    # ✅ NEW: Send single invoice immediately
    @action(detail=True, methods=['post'])
    def send_single(self, request, pk=None):
        """
        Send a single invoice immediately without batching.
        Useful for urgent deliveries or COD.
        """
        invoice = self.get_object()
        
        if invoice.status not in ['issued']:
            return Response(
                {"error": f"Cannot send invoice in '{invoice.status}' status"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                invoice.status = 'sent'
                invoice.batch_sent_date = timezone.now()
                invoice.save(update_fields=['status', 'batch_sent_date'])
                
                # Send email
                from .tasks import send_single_invoice_email
                send_single_invoice_email.delay(str(invoice.id))
                
                return Response({
                    "message": "Invoice sent successfully",
                    "invoice": InvoiceSerializer(invoice).data
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def send_reminder(self, request, pk=None):
        """Send payment reminder for overdue invoice"""
        invoice = self.get_object()
        
        if invoice.payment_status == 'paid':
            return Response(
                {"error": "Invoice is already paid"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invoice.last_reminder_sent = timezone.now()
        invoice.save(update_fields=['last_reminder_sent'])
        
        from .tasks import send_payment_reminder
        send_payment_reminder.delay(str(invoice.id))
        
        return Response(
            {"message": "Payment reminder sent"},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def cancel_invoice(self, request, pk=None):
        """Cancel an invoice"""
        invoice = self.get_object()
        
        if invoice.payment_status == 'paid':
            return Response(
                {"error": "Cannot cancel paid invoice"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reason = request.data.get('reason', '')
        
        invoice.status = 'cancelled'
        invoice.internal_notes += f"\n[Cancelled by {request.user.get_full_name()} on {timezone.now()}]: {reason}"
        invoice.save()
        
        return Response(
            {"message": "Invoice cancelled"},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get invoice summary statistics"""
        qs = self.get_queryset()
        
        summary = qs.aggregate(
            total_invoices=Count('id'),
            total_amount=Sum('total_amount'),
            total_paid=Sum('amount_paid'),
            total_due=Sum('amount_due')
        )
        
        # Status breakdown
        by_status = qs.values('status').annotate(
            count=Count('id'),
            total=Sum('amount_due')
        )
        
        # Payment status breakdown
        by_payment_status = qs.values('payment_status').annotate(
            count=Count('id'),
            total=Sum('amount_due')
        )
        
        # Convert Decimals to float
        for key in ['total_amount', 'total_paid', 'total_due']:
            if summary.get(key) is not None:
                summary[key] = float(summary[key])
        
        for item in list(by_status) + list(by_payment_status):
            if item.get('total') is not None:
                item['total'] = float(item['total'])
        
        return Response({
            'summary': summary,
            'by_status': list(by_status),
            'by_payment_status': list(by_payment_status)
        })

    @action(detail=False, methods=['get'])
    def aging(self, request):
        """Get accounts receivable aging report"""
        today = timezone.now().date()
        
        # Current
        current = Invoice.objects.filter(
            status__in=['issued', 'sent'],
            due_date__gte=today
        ).aggregate(total=Sum('amount_due'))['total'] or Decimal('0.00')
        
        # 1-30 days
        days_1_30 = Invoice.objects.filter(
            status__in=['overdue', 'sent'],
            due_date__lt=today,
            due_date__gte=today - timedelta(days=30)
        ).aggregate(total=Sum('amount_due'))['total'] or Decimal('0.00')
        
        # 31-60 days
        days_31_60 = Invoice.objects.filter(
            status__in=['overdue', 'sent'],
            due_date__lt=today - timedelta(days=30),
            due_date__gte=today - timedelta(days=60)
        ).aggregate(total=Sum('amount_due'))['total'] or Decimal('0.00')
        
        # 61-90 days
        days_61_90 = Invoice.objects.filter(
            status__in=['overdue', 'sent'],
            due_date__lt=today - timedelta(days=60),
            due_date__gte=today - timedelta(days=90)
        ).aggregate(total=Sum('amount_due'))['total'] or Decimal('0.00')
        
        # Over 90
        over_90 = Invoice.objects.filter(
            status__in=['overdue', 'sent'],
            due_date__lt=today - timedelta(days=90)
        ).aggregate(total=Sum('amount_due'))['total'] or Decimal('0.00')
        
        total = current + days_1_30 + days_31_60 + days_61_90 + over_90
        
        return Response({
            'current': float(current),
            'days_1_30': float(days_1_30),
            'days_31_60': float(days_31_60),
            'days_61_90': float(days_61_90),
            'over_90_days': float(over_90),
            'total': float(total)
        })


class InvoiceBatchViewSet(ModelViewSet):
    """
    ✅ NEW: Manage invoice batches.
    View history of batched invoices sent to buyers.
    """
    queryset = InvoiceBatch.objects.select_related('account', 'created_by')
    serializer_class = InvoiceBatchSerializer
    permission_classes = [IsAuthenticated, IsFinance | IsSuperAdmin]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['account', 'sent_via_email']
    ordering_fields = ['batch_date', 'total_amount']
    ordering = ['-batch_date']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        
        if user.role in ['super_admin', 'finance']:
            return super().get_queryset()
        
        return super().get_queryset().none()

    @action(detail=True, methods=['get'])
    def invoices(self, request, pk=None):
        """Get all invoices in this batch"""
        batch = self.get_object()
        
        invoices = Invoice.objects.filter(batch_id=batch.batch_number)
        serializer = InvoiceListSerializer(invoices, many=True)
        
        return Response({
            'batch': InvoiceBatchSerializer(batch).data,
            'invoices': serializer.data
        })


class PaymentViewSet(ModelViewSet):
    """Payment management with reconciliation"""
    queryset = Payment.objects.select_related('invoice__account', 'created_by', 'reconciled_by')
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, IsFinance | IsSuperAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'payment_method', 'reconciled', 'invoice']
    search_fields = ['payment_number', 'reference_number', 'transaction_id']
    ordering_fields = ['payment_date', 'amount']
    ordering = ['-payment_date']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        qs = super().get_queryset()
        
        if user.role in ['super_admin', 'finance']:
            return qs
        elif user.role == 'client':
            account_ids = user.contact_accounts.values_list('account_id', flat=True)
            return qs.filter(invoice__account__in=account_ids)
        
        return qs.none()

    @action(detail=True, methods=['post'])
    def reconcile(self, request, pk=None):
        """Reconcile a payment"""
        payment = self.get_object()
        
        if payment.reconciled:
            return Response(
                {"error": "Payment already reconciled"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payment.reconciled = True
        payment.reconciled_date = timezone.now()
        payment.reconciled_by = request.user
        payment.save()
        
        return Response(
            {"message": "Payment reconciled successfully"},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get payment summary statistics"""
        qs = self.get_queryset()
        
        summary = qs.aggregate(
            total_payments=Count('id'),
            total_amount=Sum('amount'),
            completed_amount=Sum('amount', filter=Q(status='completed')),
            pending_amount=Sum('amount', filter=Q(status='pending')),
            reconciled_count=Count('id', filter=Q(reconciled=True))
        )
        
        # Convert to float
        for key in ['total_amount', 'completed_amount', 'pending_amount']:
            if summary.get(key):
                summary[key] = float(summary[key])
        
        return Response({'summary': summary})


class JournalEntryViewSet(ModelViewSet):
    queryset = JournalEntry.objects.select_related(
        'created_by', 'related_trade', 'related_invoice', 'related_payment'
    )
    serializer_class = JournalEntrySerializer  # ← Now valid
    permission_classes = [IsAuthenticated, IsFinance | IsSuperAdmin]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['entry_type', 'debit_account', 'credit_account']
    ordering_fields = ['entry_date', 'amount']
    ordering = ['-entry_date']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset.none()
        return super().get_queryset()


class BudgetViewSet(ModelViewSet):
    queryset = Budget.objects.select_related('hub', 'grain_type')
    serializer_class = BudgetSerializer  # ← Now valid
    permission_classes = [IsAuthenticated, IsFinance | IsSuperAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['period', 'hub', 'grain_type']
    ordering = ['-period']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset.none()
        return super().get_queryset()