# reports/views.py - FIXED VERSION
import traceback
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
import os

from .models import ReportExport, ReportSchedule
from .serializers import (
    ReportExportSerializer,
    ReportScheduleSerializer,
    SupplierReportFilterSerializer,
    TradeReportFilterSerializer,
    InvoiceReportFilterSerializer,
    PaymentReportFilterSerializer,
    DepositorReportFilterSerializer,
    VoucherReportFilterSerializer,
    InventoryReportFilterSerializer,
    InvestorReportFilterSerializer,
)
from .permissions import CanGenerateReports, CanViewAllReports, CanScheduleReports
from .utils import (
    generate_report_data,
    export_to_csv,
    export_to_excel,
    export_to_pdf,
    logger,
)


def sanitize_filters_for_json(filters):
    """
    ✅ NEW: Convert sets to lists in filters dict to make it JSON serializable.
    This is necessary because MultipleChoiceField can return sets.
    """
    sanitized = {}
    for key, value in filters.items():
        if isinstance(value, set):
            sanitized[key] = list(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_filters_for_json(value)
        elif isinstance(value, (list, tuple)):
            sanitized[key] = [
                list(item) if isinstance(item, set) else item 
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


class ReportExportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for managing report exports.
    List and retrieve generated reports.
    """
    serializer_class = ReportExportSerializer
    permission_classes = [IsAuthenticated, CanGenerateReports]
    
    def get_queryset(self):
        user = self.request.user
        queryset = ReportExport.objects.select_related('generated_by', 'hub')
        
        # Super admins and finance can see all reports
        if user.role in ['super_admin', 'finance']:
            return queryset
        
        # Hub admins see only their hub's reports
        if user.role == 'hub_admin' and hasattr(user, 'hub'):
            return queryset.filter(Q(hub=user.hub) | Q(hub__isnull=True))
        
        # Others see only their own reports
        return queryset.filter(generated_by=user)
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download a generated report"""
        report_export = self.get_object()
        
        # Check if expired
        if report_export.is_expired():
            return Response(
                {'error': 'Report download link has expired'},
                status=status.HTTP_410_GONE
            )
        
        # Check if completed
        if report_export.status != 'completed':
            return Response(
                {'error': 'Report is not ready for download'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if file exists
        if not report_export.file_path or not os.path.exists(report_export.file_path):
            return Response(
                {'error': 'Report file not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Determine content type
        content_types = {
            'pdf': 'application/pdf',
            'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'csv': 'text/csv',
        }
        content_type = content_types.get(report_export.format, 'application/octet-stream')
        
        # Generate filename
        filename = f"{report_export.report_type}_report_{report_export.requested_at.strftime('%Y%m%d')}.{report_export.format}"
        
        # Return file
        response = FileResponse(
            open(report_export.file_path, 'rb'),
            content_type=content_type
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    @action(detail=False, methods=['get'])
    def cleanup_expired(self, request):
        """Cleanup expired reports (admin only)"""
        if request.user.role != 'super_admin':
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        expired_reports = ReportExport.objects.filter(
            expires_at__lt=timezone.now()
        )
        
        count = 0
        for report in expired_reports:
            if report.file_path and os.path.exists(report.file_path):
                os.remove(report.file_path)
            report.delete()
            count += 1
        
        return Response({
            'message': f'Cleaned up {count} expired reports'
        })


class ReportScheduleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing scheduled reports.
    """
    serializer_class = ReportScheduleSerializer
    permission_classes = [IsAuthenticated, CanScheduleReports]
    
    def get_queryset(self):
        user = self.request.user
        queryset = ReportSchedule.objects.select_related(
            'created_by', 'hub'
        ).prefetch_related('recipients')
        
        # Super admins and finance can see all schedules
        if user.role in ['super_admin', 'finance']:
            return queryset
        
        # Hub admins see only their hub's schedules
        if user.role == 'hub_admin' and hasattr(user, 'hub'):
            return queryset.filter(Q(hub=user.hub) | Q(hub__isnull=True))
        
        # Others see schedules they created
        return queryset.filter(created_by=user)
    
    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        """Manually trigger a scheduled report"""
        schedule = self.get_object()
        
        # ✅ Sanitize filters before creating report export
        sanitized_filters = sanitize_filters_for_json(schedule.filters)
        
        # Create a report export
        report_export = ReportExport.objects.create(
            report_type=schedule.report_type,
            format=schedule.format,
            filters=sanitized_filters,  # ✅ Use sanitized filters
            generated_by=request.user,
            hub=schedule.hub,
            status='pending'
        )
        
        # TODO: Trigger async task to generate report
        # For now, return the export object
        
        serializer = ReportExportSerializer(report_export, context={'request': request})
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle schedule active status"""
        schedule = self.get_object()
        schedule.is_active = not schedule.is_active
        schedule.save()
        
        serializer = self.get_serializer(schedule)
        return Response(serializer.data)


class BaseReportGenerationView(generics.GenericAPIView):
    """Base view for report generation"""
    permission_classes = [IsAuthenticated, CanGenerateReports]
    report_type = None
    filter_serializer_class = None
    
    def post(self, request):
        # Validate filters
        filter_serializer = self.filter_serializer_class(data=request.data)
        filter_serializer.is_valid(raise_exception=True)
        
        filters = filter_serializer.validated_data
        export_format = filters.pop('format', 'pdf')
        
        # ✅ CRITICAL FIX: Sanitize filters to convert sets to lists
        sanitized_filters = sanitize_filters_for_json(filters)
        
        # Create report export record
        report_export = ReportExport.objects.create(
            report_type=self.report_type,
            format=export_format,
            filters=sanitized_filters,  # ✅ Use sanitized filters
            generated_by=request.user,
            hub=getattr(request.user, 'hub', None),
            status='processing'
        )
        
        try:
            # Generate report data - use original filters (not sanitized)
            data = generate_report_data(self.report_type, filters)
            
            # Prepare data for export
            export_data = self.prepare_export_data(data)
            columns = self.get_columns()
            
            # Generate file
            file_content = self.generate_file(export_data, columns, export_format)
            
            # Save file
            file_path = self.save_file(report_export, file_content, export_format)
            
            # Mark as completed
            report_export.mark_completed(file_path, len(export_data))
            
            serializer = ReportExportSerializer(report_export, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            logger.error(traceback.format_exc())
            report_export.mark_failed(str(e))
            return Response(
                {'error': f'Failed to generate report: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def prepare_export_data(self, data):
        """Override in subclass to prepare data for export"""
        return data
    
    def get_columns(self):
        """Override in subclass to define columns"""
        return []
    
    def generate_file(self, data, columns, export_format):
        """Generate file based on format"""
        title = f"{self.report_type.replace('_', ' ').title()} Report"
        
        if export_format == 'csv':
            return export_to_csv(data, columns)
        elif export_format == 'excel':
            return export_to_excel(data, columns, title)
        elif export_format == 'pdf':
            return export_to_pdf(data, columns, title)
        else:
            raise ValueError(f"Unsupported format: {export_format}")
    
    def save_file(self, report_export, file_content, export_format):
        """Save file to disk"""
        from django.conf import settings
        
        # Create reports directory if it doesn't exist
        reports_dir = os.path.join(settings.MEDIA_ROOT, 'reports')
        os.makedirs(reports_dir, exist_ok=True)
        
        # Generate filename
        filename = f"{report_export.id}.{export_format}"
        file_path = os.path.join(reports_dir, filename)
        
        # Write file
        mode = 'wb' if isinstance(file_content, bytes) else 'w'
        with open(file_path, mode) as f:
            f.write(file_content)
        
        # Store file size
        report_export.file_size = os.path.getsize(file_path)
        report_export.save()
        
        return file_path


# ... [Rest of the view classes remain the same - GenerateSupplierReportView, etc.]
# I'll include the key ones below:

class GenerateSupplierReportView(BaseReportGenerationView):
    """Generate supplier report"""
    report_type = 'supplier'
    filter_serializer_class = SupplierReportFilterSerializer
    
    def get_columns(self):
        return [
            'supplier_name', 'phone_number', 'total_trades',
            'total_quantity_kg', 'total_value', 'avg_price_per_kg'
        ]
    
    def prepare_export_data(self, data):
        return [
            {
                'supplier_name': f"{row['supplier__first_name']} {row['supplier__last_name']}",
                'phone_number': row['supplier__phone_number'],
                'total_trades': row['total_trades'],
                'total_quantity_kg': row['total_quantity_kg'],
                'total_value': row['total_value'],
                'avg_price_per_kg': row['avg_price_per_kg'],
            }
            for row in data
        ]


class GenerateTradeReportView(BaseReportGenerationView):
    """Generate trade report"""
    report_type = 'trade'
    filter_serializer_class = TradeReportFilterSerializer
    
    def get_columns(self):
        return [
            'trade_number', 'date', 'buyer', 'supplier', 'grain_type',
            'quantity_kg', 'buying_price', 'selling_price',
            'total_trade_cost', 'payable_by_buyer', 'margin', 'status'
        ]
    
    def prepare_export_data(self, data):
        export_data = []
        
        for trade in data:
            buyer_name = trade.buyer.name if trade.buyer else 'N/A'
            
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
        
        return export_data


class GenerateInvoiceReportView(BaseReportGenerationView):
    """Generate invoice report"""
    report_type = 'invoice'
    filter_serializer_class = InvoiceReportFilterSerializer
    
    def get_columns(self):
        return [
            'invoice_number', 'issue_date', 'due_date', 'account',
            'total_amount', 'amount_paid', 'amount_due', 'payment_status'
        ]
    
    def prepare_export_data(self, data):
        return [
            {
                'invoice_number': invoice.invoice_number,
                'issue_date': invoice.issue_date.strftime('%Y-%m-%d'),
                'due_date': invoice.due_date.strftime('%Y-%m-%d'),
                'account': invoice.account.name,
                'total_amount': float(invoice.total_amount),
                'amount_paid': float(invoice.amount_paid),
                'amount_due': float(invoice.amount_due),
                'payment_status': invoice.payment_status,
            }
            for invoice in data
        ]


class GeneratePaymentReportView(BaseReportGenerationView):
    """Generate payment report"""
    report_type = 'payment'
    filter_serializer_class = PaymentReportFilterSerializer
    
    def get_columns(self):
        return [
            'payment_date', 'invoice_number', 'account', 'amount',
            'payment_method', 'reference_number', 'created_by'
        ]
    
    def prepare_export_data(self, data):
        return [
            {
                'payment_date': payment.payment_date.strftime('%Y-%m-%d'),
                'invoice_number': payment.invoice.invoice_number,
                'account': payment.invoice.account.name,
                'amount': float(payment.amount),
                'payment_method': payment.payment_method,
                'reference_number': payment.reference_number or 'N/A',
                'created_by': payment.created_by.phone_number if payment.created_by else 'N/A',
            }
            for payment in data
        ]


class GenerateDepositorReportView(BaseReportGenerationView):
    """Generate depositor report"""
    report_type = 'depositor'
    filter_serializer_class = DepositorReportFilterSerializer
    
    def get_columns(self):
        return [
            'farmer_name', 'phone_number', 'deposit_date', 'grain_type',
            'quantity_kg', 'quality_grade', 'hub', 'validated'
        ]
    
    def prepare_export_data(self, data):
        return [
            {
                'farmer_name': f"{deposit.farmer.first_name} {deposit.farmer.last_name}",
                'phone_number': deposit.farmer.phone_number,
                'deposit_date': deposit.deposit_date.strftime('%Y-%m-%d'),
                'grain_type': deposit.grain_type.name,
                'quantity_kg': float(deposit.quantity_kg),
                'quality_grade': deposit.quality_grade.name if deposit.quality_grade else 'N/A',
                'hub': deposit.hub.name,
                'validated': 'Yes' if deposit.validated else 'No',
            }
            for deposit in data
        ]


class GenerateVoucherReportView(BaseReportGenerationView):
    """Generate voucher report"""
    report_type = 'voucher'
    filter_serializer_class = VoucherReportFilterSerializer
    
    def get_columns(self):
        return [
            'voucher_id', 'issue_date', 'farmer', 'grain_type',
            'quantity_kg', 'holder', 'status', 'verification_status'
        ]
    
    def prepare_export_data(self, data):
        return [
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


class GenerateInventoryReportView(BaseReportGenerationView):
    """Generate inventory report"""
    report_type = 'inventory'
    filter_serializer_class = InventoryReportFilterSerializer
    
    def get_columns(self):
        return [
            'hub', 'grain_type', 'total_quantity_kg', 'available_quantity_kg'
        ]
    
    def prepare_export_data(self, data):
        return [
            {
                'hub': inventory.hub.name,
                'grain_type': inventory.grain_type.name,
                'total_quantity_kg': float(inventory.total_quantity_kg),
                'available_quantity_kg': float(inventory.available_quantity_kg),
            }
            for inventory in data
        ]


class GenerateInvestorReportView(BaseReportGenerationView):
    """Generate investor report"""
    report_type = 'investor'
    filter_serializer_class = InvestorReportFilterSerializer
    
    def get_columns(self):
        return [
            'investor_name', 'phone_number', 'total_deposited',
            'total_utilized', 'available_balance', 'total_returns'
        ]
    
    def prepare_export_data(self, data):
        return [
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


class DashboardStatsView(generics.GenericAPIView):
    """Get dashboard statistics"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            from trade.models import Trade
            from accounting.models import Invoice, Payment
            from vouchers.models import Deposit, Voucher
            
            # Date range for statistics
            today = timezone.now().date()
            month_ago = today - timedelta(days=30)
            
            # Trade statistics
            trades_count = Trade.objects.filter(created_at__gte=month_ago).count()
            trades_value = Trade.objects.filter(
                created_at__gte=month_ago,
                status__in=['delivered', 'completed']
            ).aggregate(total=Sum('total_trade_cost'))['total'] or 0
            
            # Invoice statistics
            invoices_count = Invoice.objects.filter(issue_date__gte=month_ago).count()
            invoices_overdue = Invoice.objects.filter(
                payment_status='overdue',
                due_date__lt=today
            ).count()
            
            # Payment statistics
            payments_count = Payment.objects.filter(payment_date__gte=month_ago).count()
            payments_value = Payment.objects.filter(
                payment_date__gte=month_ago,
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            # Deposit statistics
            deposits_count = Deposit.objects.filter(deposit_date__gte=month_ago).count()
            deposits_quantity = Deposit.objects.filter(
                deposit_date__gte=month_ago
            ).aggregate(total=Sum('quantity_kg'))['total'] or 0
            
            # Voucher statistics
            vouchers_active = Voucher.objects.filter(status='issued').count()
            
            return Response({
                'trades': {
                    'count': trades_count,
                    'value': float(trades_value),
                },
                'invoices': {
                    'count': invoices_count,
                    'overdue_count': invoices_overdue,
                },
                'payments': {
                    'count': payments_count,
                    'value': float(payments_value),
                },
                'deposits': {
                    'count': deposits_count,
                    'quantity_kg': float(deposits_quantity),
                },
                'vouchers': {
                    'active_count': vouchers_active,
                },
                'period': {
                    'start_date': month_ago.isoformat(),
                    'end_date': today.isoformat(),
                }
            })
            
        except Exception as e:
            logger.error(f"Error generating dashboard stats: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                {'error': f'Failed to generate dashboard stats: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )