# trade/views.py - ENHANCED VERSION with proper multi-GRN handling

from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Q, Avg, Count
from django.utils import timezone
from decimal import Decimal

from .models import Trade, TradeFinancing, TradeLoan, TradeCost, Brokerage, GoodsReceivedNote
from .serializers import (
    TradeSerializer, TradeListSerializer, TradeFinancingSerializer,
    TradeLoanSerializer, TradeCostSerializer, BrokerageSerializer,
    GoodsReceivedNoteSerializer, VoucherAllocationSerializer
)
from rest_framework.filters import SearchFilter, OrderingFilter


class TradeViewSet(ModelViewSet):
    """Trade management with proper multi-GRN/multi-invoice support"""
    queryset = Trade.objects.select_related(
        'buyer', 'supplier', 'grain_type', 'quality_grade', 'hub',
        'initiated_by', 'approved_by'
    ).prefetch_related('vouchers', 'additional_costs', 'brokerages', 'financing_allocations', 'loans', 'grns')
    
    serializer_class = TradeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]
    search_fields = ['trade_number', 'buyer__name', 'remarks']
    ordering_fields = ['created_at', 'payable_by_buyer', 'margin', 'delivery_date']
    ordering = ['-created_at']
    filterset_fields = ['status', 'hub', 'buyer', 'grain_type']

    def get_serializer_class(self):
        if self.action == 'list':
            return TradeListSerializer
        return TradeSerializer

    def get_queryset(self):
        """Permission-based filtering"""
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
            
        user = self.request.user
        qs = super().get_queryset()
        
        if user.role in ['super_admin', 'finance']:
            pass  # See all
        elif user.role in ['bdm', 'agent']:
            hub_ids = user.hub_memberships.filter(status='active').values_list('hub_id', flat=True)
            qs = qs.filter(Q(initiated_by=user) | Q(hub__in=hub_ids))
        elif user.role == 'client':
            account_ids = user.contact_accounts.values_list('account_id', flat=True)
            qs = qs.filter(buyer__in=account_ids)
        elif user.role == 'hub_admin':
            hub_ids = user.hub_memberships.filter(role='hub_admin', status='active').values_list('hub_id', flat=True)
            qs = qs.filter(hub__in=hub_ids)
        elif user.role == 'investor':
            qs = qs.filter(
                Q(financing_allocations__investor_account__investor=user) |
                Q(loans__investor_account__investor=user)
            ).distinct()
        else:
            return qs.none()
        
        return qs

    @action(detail=True, methods=['post'])
    def create_delivery_batch(self, request, pk=None):
        """
        ✅ NEW: Create a GRN for a partial or full delivery.
        This automatically creates an invoice via signal.
        
        Supports multiple deliveries per trade.
        
        POST /api/trade/trades/{id}/create_delivery_batch/
        Body: {
            "quantity_kg": 5000,  # Partial delivery
            "vehicle_number": "UAX 123A",
            "driver_name": "John Doe",
            ...other GRN fields
        }
        """
        trade = self.get_object()
        
        # Validate trade status
        if trade.status not in ['ready_for_delivery', 'in_transit', 'delivered']:
            return Response({
                "error": f"Cannot create delivery for trade in '{trade.status}' status",
                "message": "Trade must be 'ready_for_delivery', 'in_transit', or 'delivered'"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check remaining quantity
        delivered_so_far = trade.grns.aggregate(
            total=Sum('net_weight_kg')
        )['total'] or Decimal('0.00')
        
        remaining_qty = trade.quantity_kg - delivered_so_far
        
        if remaining_qty <= 0:
            return Response({
                "error": "Trade order fully delivered",
                "total_ordered": float(trade.quantity_kg),
                "delivered_so_far": float(delivered_so_far),
                "remaining": 0.0
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate requested quantity
        requested_qty = Decimal(str(request.data.get('net_weight_kg', 0)))
        if requested_qty <= 0:
            return Response({
                "error": "net_weight_kg must be greater than 0"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if requested_qty > remaining_qty:
            return Response({
                "error": f"Requested quantity ({requested_qty} kg) exceeds remaining quantity ({remaining_qty} kg)",
                "total_ordered": float(trade.quantity_kg),
                "delivered_so_far": float(delivered_so_far),
                "remaining": float(remaining_qty)
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Create GRN
                grn_data = request.data.copy()
                grn_data['trade'] = str(trade.id)
                
                grn_serializer = GoodsReceivedNoteSerializer(
                    data=grn_data,
                    context={'request': request}
                )
                
                if grn_serializer.is_valid():
                    grn = grn_serializer.save()
                    
                    # Update trade status if first delivery
                    if trade.status == 'ready_for_delivery':
                        trade.status = 'in_transit'
                        trade.save(update_fields=['status'])
                    
                    # Check if trade is now fully delivered
                    new_total_delivered = delivered_so_far + requested_qty
                    is_fully_delivered = new_total_delivered >= trade.quantity_kg
                    
                    if is_fully_delivered:
                        trade.status = 'delivered'
                        trade.delivery_status = 'delivered'
                        trade.actual_delivery_date = grn.delivery_date
                        trade.save(update_fields=['status', 'delivery_status', 'actual_delivery_date'])
                    
                    # Get the auto-generated invoice
                    invoice = None
                    try:
                        from accounting.models import Invoice
                        invoice = Invoice.objects.get(grn=grn)
                    except Invoice.DoesNotExist:
                        pass
                    
                    return Response({
                        "message": "Delivery batch created successfully",
                        "grn": {
                            "id": str(grn.id),
                            "grn_number": grn.grn_number,
                            "delivery_date": grn.delivery_date,
                            "net_weight_kg": float(grn.net_weight_kg),
                            "vehicle_number": grn.vehicle_number,
                            "driver_name": grn.driver_name
                        },
                        "invoice": {
                            "id": str(invoice.id),
                            "invoice_number": invoice.invoice_number,
                            "total_amount": float(invoice.total_amount),
                            "due_date": invoice.due_date,
                            "status": invoice.status
                        } if invoice else None,
                        "trade_status": {
                            "status": trade.status,
                            "total_ordered_kg": float(trade.quantity_kg),
                            "delivered_so_far_kg": float(new_total_delivered),
                            "remaining_kg": float(trade.quantity_kg - new_total_delivered),
                            "is_fully_delivered": is_fully_delivered,
                            "delivery_count": trade.grns.count()
                        }
                    }, status=status.HTTP_201_CREATED)
                else:
                    return Response({
                        "error": "Invalid GRN data",
                        "details": grn_serializer.errors
                    }, status=status.HTTP_400_BAD_REQUEST)
                    
        except Exception as e:
            import traceback
            print("Error creating delivery batch:", traceback.format_exc())
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def delivery_progress(self, request, pk=None):
        """
        ✅ NEW: Get detailed delivery progress for a trade.
        Shows all GRNs, invoices, and remaining quantity.
        
        GET /api/trade/trades/{id}/delivery_progress/
        """
        trade = self.get_object()
        
        # Get all GRNs with their invoices
        grns = trade.grns.select_related('invoice').order_by('delivery_date')
        
        deliveries = []
        total_delivered = Decimal('0.00')
        
        for grn in grns:
            total_delivered += grn.net_weight_kg
            
            # Get invoice info
            invoice_info = None
            try:
                invoice = grn.invoice
                invoice_info = {
                    "invoice_number": invoice.invoice_number,
                    "total_amount": float(invoice.total_amount),
                    "amount_paid": float(invoice.amount_paid),
                    "amount_due": float(invoice.amount_due),
                    "status": invoice.status,
                    "payment_status": invoice.payment_status,
                    "due_date": invoice.due_date.isoformat(),
                    "is_overdue": invoice.payment_status == 'overdue'
                }
            except:
                invoice_info = {"error": "Invoice not created"}
            
            deliveries.append({
                "grn_number": grn.grn_number,
                "delivery_date": grn.delivery_date.isoformat(),
                "net_weight_kg": float(grn.net_weight_kg),
                "vehicle_number": grn.vehicle_number,
                "driver_name": grn.driver_name,
                "invoice": invoice_info
            })
        
        remaining_qty = trade.quantity_kg - total_delivered
        completion_percentage = (total_delivered / trade.quantity_kg * 100) if trade.quantity_kg > 0 else 0
        
        # Payment summary across all invoices
        try:
            from accounting.models import Invoice
            invoices = Invoice.objects.filter(trade=trade)
            payment_summary = invoices.aggregate(
                total_invoiced=Sum('total_amount'),
                total_paid=Sum('amount_paid'),
                total_due=Sum('amount_due')
            )
            
            all_invoices_paid = not invoices.filter(
                payment_status__in=['unpaid', 'partial', 'overdue']
            ).exists()
            
        except:
            payment_summary = {
                'total_invoiced': 0,
                'total_paid': 0,
                'total_due': 0
            }
            all_invoices_paid = False
        
        return Response({
            "trade_number": trade.trade_number,
            "buyer": trade.buyer.name,
            "status": trade.status,
            "delivery_summary": {
                "total_ordered_kg": float(trade.quantity_kg),
                "total_delivered_kg": float(total_delivered),
                "remaining_kg": float(remaining_qty),
                "completion_percentage": float(completion_percentage),
                "is_fully_delivered": remaining_qty <= 0,
                "delivery_count": len(deliveries),
                "can_create_more_deliveries": remaining_qty > 0 and trade.status in ['ready_for_delivery', 'in_transit', 'delivered']
            },
            "deliveries": deliveries,
            "payment_summary": {
                "total_invoiced": float(payment_summary.get('total_invoiced') or 0),
                "total_paid": float(payment_summary.get('total_paid') or 0),
                "total_due": float(payment_summary.get('total_due') or 0),
                "all_paid": all_invoices_paid
            },
            "next_steps": self._get_next_steps(trade, remaining_qty, all_invoices_paid)
        })

    def _get_next_steps(self, trade, remaining_qty, all_invoices_paid):
        """Helper to determine next steps"""
        steps = []
        
        if trade.status == 'draft':
            steps.append("Submit trade for approval")
        elif trade.status == 'pending_approval':
            steps.append("Wait for trade approval")
        elif trade.status == 'approved':
            if trade.requires_financing and not trade.financing_complete:
                steps.append("Complete investor financing allocation")
            else:
                steps.append("Progress to 'ready_for_delivery'")
        elif trade.status in ['ready_for_delivery', 'in_transit']:
            if remaining_qty > 0:
                steps.append(f"Create delivery batch for remaining {remaining_qty} kg")
            else:
                steps.append("All deliveries completed - mark as delivered")
        elif trade.status == 'delivered':
            if not all_invoices_paid:
                steps.append("Collect payment for outstanding invoices")
            else:
                steps.append("All invoices paid - mark trade as completed")
        elif trade.status == 'completed':
            steps.append("Trade is complete!")
        
        return steps

    @action(detail=True, methods=['post'])
    def progress_status(self, request, pk=None):
        """
        Progress trade to next status.
        Simplified - no GRN creation here, use create_delivery_batch instead.
        """
        trade = self.get_object()
        notes = request.data.get('notes', '')
        
        # Vehicle info (for in_transit status)
        vehicle_number = request.data.get('vehicle_number')
        driver_name = request.data.get('driver_name')
        driver_phone = request.data.get('driver_phone')
        
        try:
            with transaction.atomic():
                old_status = trade.status
                next_status = trade.progress_to_next_status(user=request.user, notes=notes)
                
                # Update vehicle info if transitioning to in_transit
                if next_status == 'in_transit':
                    if vehicle_number:
                        trade.vehicle_number = vehicle_number
                    if driver_name:
                        trade.driver_name = driver_name
                    if driver_phone:
                        trade.driver_phone = driver_phone
                    trade.save(update_fields=['vehicle_number', 'driver_name', 'driver_phone'])
                
                return Response({
                    "message": f"Trade progressed from '{old_status}' to '{next_status}'",
                    "old_status": old_status,
                    "new_status": next_status,
                    "trade": TradeSerializer(trade, context={'request': request}).data
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def mark_completed(self, request, pk=None):
        """
        ✅ NEW: Manually mark trade as completed.
        Validates that all invoices are paid first.
        
        POST /api/trade/trades/{id}/mark_completed/
        """
        trade = self.get_object()
        
        if trade.status != 'delivered':
            return Response({
                "error": f"Cannot complete trade in '{trade.status}' status",
                "message": "Trade must be 'delivered' first"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if all invoices are paid
        try:
            from accounting.models import Invoice
            unpaid_invoices = Invoice.objects.filter(
                trade=trade,
                payment_status__in=['unpaid', 'partial', 'overdue']
            )
            
            if unpaid_invoices.exists():
                unpaid_list = [
                    {
                        "invoice_number": inv.invoice_number,
                        "amount_due": float(inv.amount_due),
                        "payment_status": inv.payment_status
                    }
                    for inv in unpaid_invoices
                ]
                
                return Response({
                    "error": "Cannot complete trade with unpaid invoices",
                    "unpaid_invoices": unpaid_list,
                    "total_outstanding": float(sum(inv.amount_due for inv in unpaid_invoices))
                }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            return Response({
                "error": f"Error checking invoice status: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Mark as completed
        trade.status = 'completed'
        trade.save(update_fields=['status'])
        
        return Response({
            "message": "Trade marked as completed",
            "trade": TradeSerializer(trade, context={'request': request}).data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def invoices_and_payments(self, request, pk=None):
        """
        Get all invoices and their payment status for this trade.
        
        GET /api/trade/trades/{id}/invoices_and_payments/
        """
        trade = self.get_object()
        
        try:
            from accounting.models import Invoice
            from accounting.serializers import InvoiceListSerializer
            
            invoices = Invoice.objects.filter(trade=trade).prefetch_related('payments')
            
            if not invoices.exists():
                return Response({
                    'has_invoices': False,
                    'message': 'No invoices yet. Create a delivery (GRN) to generate invoice.',
                    'grn_count': trade.grns.count(),
                    'can_create_delivery': trade.status in ['ready_for_delivery', 'in_transit', 'delivered']
                })
            
            # Serialize invoices
            invoice_data = InvoiceListSerializer(invoices, many=True).data
            
            # Calculate totals
            total_invoiced = sum(inv.total_amount for inv in invoices)
            total_paid = sum(inv.amount_paid for inv in invoices)
            total_due = sum(inv.amount_due for inv in invoices)
            
            # Overall payment status
            all_paid = all(inv.payment_status == 'paid' for inv in invoices)
            any_partial = any(inv.payment_status == 'partial' for inv in invoices)
            any_overdue = any(inv.payment_status == 'overdue' for inv in invoices)
            
            if all_paid:
                overall_status = 'paid'
            elif any_partial:
                overall_status = 'partial'
            elif any_overdue:
                overall_status = 'overdue'
            else:
                overall_status = 'unpaid'
            
            return Response({
                'has_invoices': True,
                'invoice_count': invoices.count(),
                'invoices': invoice_data,
                'summary': {
                    'total_invoiced': float(total_invoiced),
                    'total_paid': float(total_paid),
                    'total_due': float(total_due),
                    'overall_status': overall_status,
                    'all_paid': all_paid
                },
                'trade_can_complete': all_paid and trade.status == 'delivered'
            })
            
        except Exception as e:
            import traceback
            print("Error in invoices_and_payments:", traceback.format_exc())
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # ... rest of your existing methods (quick_approve, quick_reject, cost_breakdown, dashboard_stats, etc.)


    @action(detail=True, methods=['post'])
    def quick_approve(self, request, pk=None):
        """Quick approve endpoint"""
        if request.user.role not in ['super_admin', 'finance']:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
        trade = self.get_object()
        
        if trade.status != 'pending_approval':
            return Response(
                {"error": f"Cannot approve trade in '{trade.status}' status"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        notes = request.data.get('notes', 'Approved')
        
        try:
            with transaction.atomic():
                trade.approved_by = request.user
                trade.approved_at = timezone.now()
                trade.internal_notes += f"\n[{timezone.now().strftime('%Y-%m-%d %H:%M')}] Approved by {request.user.get_full_name()}: {notes}"
                
                if trade.requires_financing and not trade.financing_complete:
                    trade.status = 'approved'
                else:
                    trade.status = 'ready_for_delivery'
                
                trade.save()
                
                return Response({
                    "message": "Trade approved successfully",
                    "status": trade.status,
                    "trade": TradeSerializer(trade, context={'request': request}).data
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def quick_reject(self, request, pk=None):
        """Quick reject endpoint"""
        if request.user.role not in ['super_admin', 'finance']:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
        trade = self.get_object()
        
        if trade.status not in ['pending_approval', 'draft']:
            return Response(
                {"error": f"Cannot reject trade in '{trade.status}' status"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reason = request.data.get('reason', 'Rejected')
        
        with transaction.atomic():
            trade.status = 'rejected'
            trade.internal_notes += f"\n[{timezone.now().strftime('%Y-%m-%d %H:%M')}] Rejected by {request.user.get_full_name()}: {reason}"
            trade.save()
        
        return Response({
            "message": "Trade rejected",
            "trade": TradeSerializer(trade, context={'request': request}).data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def payment_info(self, request, pk=None):
        """
        ✅ NEW: Get payment info separately
        This avoids circular imports in serializer
        """
        trade = self.get_object()
        
        try:
            from accounting.models import Invoice
            from django.db.models import Sum
            
            invoices = Invoice.objects.filter(trade=trade)
            
            if not invoices.exists():
                return Response({
                    'payment_status': 'pending',
                    'payment_status_display': 'Pending',
                    'amount_due': 0.0,
                    'amount_paid': 0.0,
                    'total_invoiced': 0.0,
                    'invoice_count': 0,
                    'invoices': []
                })
            
            # Calculate totals
            totals = invoices.aggregate(
                total_amount=Sum('total_amount'),
                amount_paid=Sum('amount_paid'),
                amount_due=Sum('amount_due')
            )
            
            # Determine payment status
            all_paid = all(inv.payment_status == 'paid' for inv in invoices)
            any_partial = any(inv.payment_status == 'partial' for inv in invoices)
            any_overdue = any(inv.payment_status == 'overdue' for inv in invoices)
            
            if all_paid:
                payment_status = 'paid'
                payment_status_display = 'Paid'
            elif any_partial:
                payment_status = 'partial'
                payment_status_display = 'Partially Paid'
            elif any_overdue:
                payment_status = 'overdue'
                payment_status_display = 'Overdue'
            else:
                payment_status = 'pending'
                payment_status_display = 'Pending'
            
            # Invoice list
            invoice_list = []
            for inv in invoices:
                invoice_list.append({
                    'id': str(inv.id),
                    'invoice_number': inv.invoice_number,
                    'grn_number': inv.grn.grn_number,
                    'total_amount': float(inv.total_amount),
                    'amount_paid': float(inv.amount_paid),
                    'amount_due': float(inv.amount_due),
                    'status': inv.status,
                    'payment_status': inv.payment_status,
                    'issue_date': inv.issue_date.isoformat(),
                    'due_date': inv.due_date.isoformat(),
                })
            
            return Response({
                'payment_status': payment_status,
                'payment_status_display': payment_status_display,
                'total_invoiced': float(totals['total_amount'] or 0),
                'amount_paid': float(totals['amount_paid'] or 0),
                'amount_due': float(totals['amount_due'] or 0),
                'invoice_count': invoices.count(),
                'invoices': invoice_list
            })
            
        except Exception as e:
            return Response(
                {"error": f"Error fetching payment info: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def cost_breakdown(self, request, pk=None):
        """Get detailed cost breakdown"""
        trade = self.get_object()
        
        additional_costs = []
        for cost in trade.additional_costs.all():
            total = cost.amount * trade.quantity_kg if cost.is_per_unit else cost.amount
            additional_costs.append({
                'cost_type': cost.cost_type,
                'description': cost.description,
                'amount': float(cost.amount),
                'is_per_unit': cost.is_per_unit,
                'total': float(total)
            })
        
        brokerages = []
        for brokerage in trade.brokerages.all():
            brokerages.append({
                'agent': f"{brokerage.agent.first_name} {brokerage.agent.last_name}".strip() if brokerage.agent else None,
                'commission_type': brokerage.commission_type,
                'commission_value': float(brokerage.commission_value),
                'amount': float(brokerage.amount),
                'notes': brokerage.notes
            })
        
        bennu_to_buyer = Decimal('0.00')
        bennu_to_seller = Decimal('0.00')
        
        if trade.bennu_fees_payer == 'buyer':
            bennu_to_buyer = trade.bennu_fees
        elif trade.bennu_fees_payer == 'seller':
            bennu_to_seller = trade.bennu_fees
        elif trade.bennu_fees_payer == 'split':
            bennu_to_buyer = trade.bennu_fees / Decimal('2')
            bennu_to_seller = trade.bennu_fees / Decimal('2')
        
        return Response({
            'purchase_cost': float(trade.buying_price * trade.quantity_kg),
            'aflatoxin_qa_cost': float(trade.aflatoxin_qa_cost),
            'weighbridge_cost': float(trade.weighbridge_cost),
            'offloading_cost': float(trade.offloading_cost),
            'loading_cost': float(trade.loading_cost),
            'transport_cost': float(trade.transport_cost_per_kg * trade.quantity_kg),
            'bennu_fees_total': float(trade.bennu_fees),
            'bennu_fees_payer': trade.bennu_fees_payer,
            'bennu_to_buyer': float(bennu_to_buyer),
            'bennu_to_seller': float(bennu_to_seller),
            'loss_quantity_kg': float(trade.loss_quantity_kg),
            'loss_cost': float(trade.loss_cost),
            'loss_reason': trade.loss_reason,
            'additional_costs': additional_costs,
            'brokerage_costs': brokerages,
            'total_trade_cost': float(trade.total_trade_cost),
            'payable_by_buyer': float(trade.payable_by_buyer),
            'margin': float(trade.margin),
            'net_profit': float(
                trade.margin - 
                sum(b.amount for b in trade.brokerages.all()) -
                sum(c.amount * trade.quantity_kg if c.is_per_unit else c.amount for c in trade.additional_costs.all())
            )
        })

    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """Get dashboard statistics"""
        qs = self.get_queryset()
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date:
            qs = qs.filter(created_at__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__lte=end_date)
        
        stats = qs.aggregate(
            total_trades=Count('id'),
            total_revenue=Sum('payable_by_buyer'),
            total_profit=Sum('margin'),
            total_quantity_kg=Sum('quantity_kg'),
            avg_roi=Avg('roi_percentage'),
            pending_approval=Count('id', filter=Q(status='pending_approval')),
            approved=Count('id', filter=Q(status='approved')),
            ready_for_delivery=Count('id', filter=Q(status='ready_for_delivery')),
            in_transit=Count('id', filter=Q(status='in_transit')),
            delivered=Count('id', filter=Q(status='delivered')),
            completed=Count('id', filter=Q(status='completed')),
        )
        
        status_breakdown = list(qs.values('status').annotate(
            count=Count('id'),
            total_value=Sum('payable_by_buyer')
        ))
        
        for item in status_breakdown:
            if item.get('total_value') is not None:
                item['total_value'] = float(item['total_value'])
        
        return Response({
            'summary': {k: float(v) if isinstance(v, Decimal) else v for k, v in stats.items()},
            'status_breakdown': status_breakdown
        })

    # Add these methods to your TradeViewSet in trade/views.py

    @action(detail=True, methods=['post'])
    def create_delivery_receipt(self, request, pk=None):
        """
        Create GRN (Goods Received Note) for a delivered trade.
        This automatically generates the invoice via signal.
        
        POST /api/trade/trades/{id}/create_delivery_receipt/
        """
        trade = self.get_object()
        
        # Validate trade status
        if trade.status not in ['in_transit', 'delivered']:
            return Response({
                "error": f"Cannot create GRN for trade in '{trade.status}' status",
                "message": "Trade must be 'in_transit' or 'delivered' to create GRN"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if GRN already exists
        if trade.grns.exists():
            return Response({
                "error": "Trade already has GRN(s)",
                "existing_grns": [
                    {
                        "grn_number": grn.grn_number,
                        "delivery_date": grn.delivery_date,
                        "net_weight_kg": float(grn.net_weight_kg)
                    }
                    for grn in trade.grns.all()
                ]
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Create GRN
                grn_data = request.data.copy()
                grn_data['trade'] = str(trade.id)
                
                grn_serializer = GoodsReceivedNoteSerializer(
                    data=grn_data,
                    context={'request': request}
                )
                
                if grn_serializer.is_valid():
                    grn = grn_serializer.save()
                    
                    # Update trade status if needed
                    if trade.status == 'in_transit':
                        trade.status = 'delivered'
                        trade.delivery_status = 'delivered'
                        trade.actual_delivery_date = grn.delivery_date
                        trade.save()
                    
                    # Get the auto-generated invoice
                    invoice = None
                    try:
                        from accounting.models import Invoice
                        invoice = Invoice.objects.get(grn=grn)
                    except Invoice.DoesNotExist:
                        pass
                    
                    return Response({
                        "message": "Delivery receipt created successfully",
                        "grn": {
                            "id": str(grn.id),
                            "grn_number": grn.grn_number,
                            "delivery_date": grn.delivery_date,
                            "net_weight_kg": float(grn.net_weight_kg),
                            "vehicle_number": grn.vehicle_number,
                            "driver_name": grn.driver_name
                        },
                        "invoice": {
                            "id": str(invoice.id),
                            "invoice_number": invoice.invoice_number,
                            "total_amount": float(invoice.total_amount),
                            "due_date": invoice.due_date,
                            "status": invoice.status
                        } if invoice else None,
                        "trade_status": trade.status
                    }, status=status.HTTP_201_CREATED)
                else:
                    return Response({
                        "error": "Invalid GRN data",
                        "details": grn_serializer.errors
                    }, status=status.HTTP_400_BAD_REQUEST)
                    
        except Exception as e:
            import traceback
            print("Error creating GRN:", traceback.format_exc())
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


    @action(detail=True, methods=['get'])
    def delivery_status_check(self, request, pk=None):
        """
        Check what's needed to complete delivery and invoicing.
        
        GET /api/trade/trades/{id}/delivery_status_check/
        """
        trade = self.get_object()
        
        # Check GRN status
        has_grn = trade.grns.exists()
        grn_list = []
        
        if has_grn:
            from accounting.models import Invoice
            for grn in trade.grns.all():
                try:
                    invoice = Invoice.objects.get(grn=grn)
                    invoice_info = {
                        "invoice_number": invoice.invoice_number,
                        "total_amount": float(invoice.total_amount),
                        "amount_paid": float(invoice.amount_paid),
                        "amount_due": float(invoice.amount_due),
                        "status": invoice.status,
                        "payment_status": invoice.payment_status
                    }
                except Invoice.DoesNotExist:
                    invoice_info = None
                
                grn_list.append({
                    "grn_number": grn.grn_number,
                    "delivery_date": grn.delivery_date,
                    "net_weight_kg": float(grn.net_weight_kg),
                    "invoice": invoice_info
                })
        
        # Determine what actions are needed
        actions_needed = []
        
        if trade.status == 'draft':
            actions_needed.append("Submit trade for approval")
        elif trade.status == 'pending_approval':
            actions_needed.append("Wait for trade approval")
        elif trade.status == 'approved':
            if trade.requires_financing and not trade.financing_complete:
                actions_needed.append("Complete investor financing allocation")
            else:
                actions_needed.append("Progress to 'ready_for_delivery'")
        elif trade.status == 'ready_for_delivery':
            actions_needed.append("Start delivery (progress to 'in_transit')")
        elif trade.status == 'in_transit':
            actions_needed.append("Mark as delivered and create GRN")
        elif trade.status == 'delivered':
            if not has_grn:
                actions_needed.append("Create Goods Received Note (GRN) to generate invoice")
            else:
                # Check payment status
                from accounting.models import Invoice
                invoices = Invoice.objects.filter(trade=trade)
                if not invoices.exists():
                    actions_needed.append("Invoice should have been auto-created with GRN")
                else:
                    unpaid_invoices = invoices.exclude(payment_status='paid')
                    if unpaid_invoices.exists():
                        actions_needed.append(f"Collect payment for {unpaid_invoices.count()} invoice(s)")
                    else:
                        actions_needed.append("All invoices paid - trade ready to be marked completed")
        elif trade.status == 'completed':
            actions_needed.append("Trade is complete!")
        
        return Response({
            "trade_number": trade.trade_number,
            "status": trade.status,
            "status_display": trade.get_status_display(),
            "has_grn": has_grn,
            "grn_count": trade.grns.count(),
            "grns": grn_list,
            "requires_financing": trade.requires_financing,
            "financing_complete": trade.financing_complete,
            "requires_voucher_allocation": trade.requires_voucher_allocation,
            "allocation_complete": trade.allocation_complete,
            "actions_needed": actions_needed,
            "next_steps": {
                "can_create_grn": trade.status in ['in_transit', 'delivered'] and not has_grn,
                "can_progress_status": trade.status not in ['completed', 'cancelled', 'rejected'],
                "needs_financing": trade.requires_financing and not trade.financing_complete,
                "needs_vouchers": trade.requires_voucher_allocation and not trade.allocation_complete
            }
        }, status=status.HTTP_200_OK)


    @action(detail=True, methods=['get'])
    def invoices_and_payments(self, request, pk=None):
        """
        Get all invoices and their payment status for this trade.
        Replacement for the payment_info endpoint with better structure.
        
        GET /api/trade/trades/{id}/invoices_and_payments/
        """
        trade = self.get_object()
        
        try:
            from accounting.models import Invoice
            from accounting.serializers import InvoiceListSerializer
            
            invoices = Invoice.objects.filter(trade=trade).prefetch_related('payments')
            
            if not invoices.exists():
                return Response({
                    'has_invoices': False,
                    'message': 'No invoices yet. Create a GRN to generate invoice.',
                    'grn_count': trade.grns.count(),
                    'can_create_grn': trade.status in ['in_transit', 'delivered']
                })
            
            # Serialize invoices
            invoice_data = InvoiceListSerializer(invoices, many=True).data
            
            # Calculate totals
            total_invoiced = sum(inv.total_amount for inv in invoices)
            total_paid = sum(inv.amount_paid for inv in invoices)
            total_due = sum(inv.amount_due for inv in invoices)
            
            # Overall payment status
            all_paid = all(inv.payment_status == 'paid' for inv in invoices)
            any_partial = any(inv.payment_status == 'partial' for inv in invoices)
            any_overdue = any(inv.payment_status == 'overdue' for inv in invoices)
            
            if all_paid:
                overall_status = 'paid'
            elif any_partial:
                overall_status = 'partial'
            elif any_overdue:
                overall_status = 'overdue'
            else:
                overall_status = 'unpaid'
            
            return Response({
                'has_invoices': True,
                'invoice_count': invoices.count(),
                'invoices': invoice_data,
                'summary': {
                    'total_invoiced': float(total_invoiced),
                    'total_paid': float(total_paid),
                    'total_due': float(total_due),
                    'overall_status': overall_status,
                    'all_paid': all_paid
                },
                'trade_can_complete': all_paid and trade.status == 'delivered'
            })
            
        except Exception as e:
            import traceback
            print("Error in invoices_and_payments:", traceback.format_exc())
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
# trade/views.py - GoodsReceivedNoteViewSet (add to your views.py)

class GoodsReceivedNoteViewSet(ModelViewSet):
    """
    GRN ViewSet with multi-delivery support.
    Each GRN automatically creates an invoice via signal.
    """
    queryset = GoodsReceivedNote.objects.select_related('trade', 'trade__buyer')
    serializer_class = GoodsReceivedNoteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['trade', 'delivery_date']
    search_fields = ['grn_number', 'vehicle_number']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        qs = super().get_queryset()
        
        if user.role in ['super_admin', 'finance']:
            return qs
        elif user.role in ['bdm', 'hub_admin']:
            from trade.models import Trade
            accessible_trades = Trade.objects.filter(
                Q(initiated_by=user) | 
                Q(hub__in=user.hub_memberships.filter(status='active').values_list('hub_id', flat=True))
            ).values_list('id', flat=True)
            return qs.filter(trade__in=accessible_trades)
        elif user.role == 'client':
            account_ids = user.contact_accounts.values_list('account_id', flat=True)
            return qs.filter(trade__buyer__in=account_ids)
        
        return qs.none()

    def perform_create(self, serializer):
        """
        Create GRN with validation for multi-delivery scenario.
        Invoice will be created automatically by signal.
        """
        with transaction.atomic():
            trade = serializer.validated_data.get('trade')
            net_weight_kg = serializer.validated_data.get('net_weight_kg')
            
            # Validate remaining quantity
            delivered_so_far = trade.grns.aggregate(
                total=Sum('net_weight_kg')
            )['total'] or Decimal('0.00')
            
            remaining_qty = trade.quantity_kg - delivered_so_far
            
            if net_weight_kg > remaining_qty:
                raise ValidationError(
                    f"Delivery quantity ({net_weight_kg} kg) exceeds remaining trade quantity ({remaining_qty} kg). "
                    f"Total ordered: {trade.quantity_kg} kg, Already delivered: {delivered_so_far} kg"
                )
            
            # Create GRN
            grn = serializer.save()
            
            # Update trade with delivery info
            trade.actual_delivery_date = grn.delivery_date
            
            # Calculate losses if any
            if grn.net_weight_kg < grn.gross_weight_kg:
                loss_in_delivery = grn.gross_weight_kg - grn.net_weight_kg
                trade.loss_quantity_kg += loss_in_delivery
                trade.loss_cost += loss_in_delivery * trade.buying_price
            
            # Check if this completes the trade delivery
            new_total_delivered = delivered_so_far + net_weight_kg
            if new_total_delivered >= trade.quantity_kg:
                trade.status = 'delivered'
                trade.delivery_status = 'delivered'
            elif trade.status == 'ready_for_delivery':
                trade.status = 'in_transit'
                trade.delivery_status = 'in_transit'
            
            trade.save()
            
            print(f"✅ GRN {grn.grn_number} created. Delivered {net_weight_kg} kg. "
                  f"Total delivered: {new_total_delivered}/{trade.quantity_kg} kg. "
                  f"Invoice will be auto-generated by signal.")

    @action(detail=True, methods=['get'])
    def invoice_status(self, request, pk=None):
        """
        Get invoice status for this GRN.
        
        GET /api/trade/grns/{id}/invoice_status/
        """
        grn = self.get_object()
        
        try:
            from accounting.models import Invoice
            invoice = Invoice.objects.get(grn=grn)
            
            from accounting.serializers import InvoiceSerializer
            return Response({
                "has_invoice": True,
                "invoice": InvoiceSerializer(invoice).data
            })
            
        except Invoice.DoesNotExist:
            return Response({
                "has_invoice": False,
                "message": "Invoice not yet created for this GRN",
                "grn_number": grn.grn_number,
                "delivery_date": grn.delivery_date
            })

    @action(detail=False, methods=['get'])
    def by_trade(self, request):
        """
        Get all GRNs for a specific trade with summary.
        
        GET /api/trade/grns/by_trade/?trade_id={trade_id}
        """
        trade_id = request.query_params.get('trade_id')
        
        if not trade_id:
            return Response({
                "error": "trade_id parameter required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from trade.models import Trade
            trade = Trade.objects.get(id=trade_id)
        except Trade.DoesNotExist:
            return Response({
                "error": "Trade not found"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get all GRNs for this trade
        grns = self.get_queryset().filter(trade=trade).order_by('delivery_date')
        
        # Calculate summary
        total_delivered = grns.aggregate(
            total=Sum('net_weight_kg')
        )['total'] or Decimal('0.00')
        
        remaining = trade.quantity_kg - total_delivered
        
        # Serialize GRNs
        serializer = self.get_serializer(grns, many=True)
        
        return Response({
            "trade_number": trade.trade_number,
            "total_ordered_kg": float(trade.quantity_kg),
            "total_delivered_kg": float(total_delivered),
            "remaining_kg": float(remaining),
            "grn_count": grns.count(),
            "is_fully_delivered": remaining <= 0,
            "grns": serializer.data
        })

class TradeFinancingViewSet(ModelViewSet):
    """ViewSet for managing investor financing allocations"""
    queryset = TradeFinancing.objects.select_related(
        'trade', 'investor_account__investor'
    )
    serializer_class = TradeFinancingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['trade', 'investor_account']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        qs = super().get_queryset()
        
        if user.role == 'super_admin':
            return qs
        elif user.role == 'finance':
            return qs
        elif user.role == 'investor':
            return qs.filter(investor_account__investor=user)
        elif user.role in ['hub_admin', 'bdm']:
            hub_ids = user.hub_memberships.filter(status='active').values_list('hub_id', flat=True)
            return qs.filter(trade__hub__in=hub_ids)
        
        return qs.none()

    def perform_create(self, serializer):
        """Create financing allocation with balance check"""
        with transaction.atomic():
            financing = serializer.save()


class TradeLoanViewSet(ModelViewSet):
    """ViewSet for managing investor loans"""
    queryset = TradeLoan.objects.select_related(
        'trade', 'investor_account__investor'
    )
    serializer_class = TradeLoanSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['trade', 'investor_account', 'status']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        qs = super().get_queryset()
        
        if user.role == 'super_admin':
            return qs
        elif user.role == 'finance':
            return qs
        elif user.role == 'investor':
            return qs.filter(investor_account__investor=user)
        elif user.role in ['hub_admin', 'bdm']:
            hub_ids = user.hub_memberships.filter(status='active').values_list('hub_id', flat=True)
            return qs.filter(trade__hub__in=hub_ids)
        
        return qs.none()

    @action(detail=True, methods=['post'])
    def repay(self, request, pk=None):
        """Record loan repayment"""
        loan = self.get_object()
        amount = Decimal(request.data.get('amount', 0))
        
        if amount <= 0:
            return Response(
                {"error": "Repayment amount must be positive"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        outstanding = loan.get_outstanding_balance()
        if amount > outstanding:
            return Response(
                {"error": f"Repayment ({amount}) exceeds outstanding balance ({outstanding})"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            loan.amount_repaid += amount
            if loan.amount_repaid >= loan.get_total_due():
                loan.status = 'repaid'
            loan.save()
            
            investor_account = loan.investor_account
            investor_account.available_balance += amount
            investor_account.total_utilized -= min(amount, loan.amount)
            investor_account.save()
            
            LedgerEntry.objects.create(
                event_type='loan_repayment',
                related_object_id=loan.id,
                user=investor_account.investor,
                hub=loan.trade.hub,
                description=f"Loan repayment of {amount} UGX for trade {loan.trade.trade_number}",
                amount=amount
            )
        
        return Response(
            {
                "message": "Repayment recorded",
                "amount_repaid": loan.amount_repaid,
                "outstanding_balance": loan.get_outstanding_balance(),
                "status": loan.status
            },
            status=status.HTTP_200_OK
        )


class TradeCostViewSet(ModelViewSet):
    """ViewSet for additional trade costs"""
    queryset = TradeCost.objects.all()
    serializer_class = TradeCostSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['trade']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        if user.role in ['super_admin', 'finance']:
            return super().get_queryset()
        
        accessible_trades = Trade.objects.filter(
            Q(initiated_by=user) | 
            Q(hub__in=user.hub_memberships.filter(status='active').values_list('hub_id', flat=True))
        ).values_list('id', flat=True)
        
        return super().get_queryset().filter(trade__in=accessible_trades)


class BrokerageViewSet(ModelViewSet):
    """ViewSet for brokerage commissions"""
    queryset = Brokerage.objects.select_related('trade', 'agent')
    serializer_class = BrokerageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['trade', 'agent']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        qs = super().get_queryset()
        
        if user.role in ['super_admin', 'finance']:
            return qs
        elif user.role in ['bdm', 'agent']:
            return qs.filter(Q(agent=user) | Q(trade__initiated_by=user))
        
        return qs.none()

    @action(detail=False, methods=['get'])
    def my_commissions(self, request):
        """Get current user's commissions"""
        user = request.user
        
        if user.role not in ['bdm', 'agent']:
            return Response(
                {"error": "Only BDMs and agents can access commissions"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        brokerages = self.get_queryset().filter(agent=user)
        
        summary = brokerages.aggregate(
            total_commissions=Sum('amount'),
            total_trades=Count('trade', distinct=True),
            avg_commission=Avg('amount')
        )
        
        if summary['total_commissions'] is not None:
            summary['total_commissions'] = float(summary['total_commissions'])
        if summary['avg_commission'] is not None:
            summary['avg_commission'] = float(summary['avg_commission'])
        
        return Response({'summary': summary})


