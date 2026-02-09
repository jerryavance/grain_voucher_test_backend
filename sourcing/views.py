# sourcing/views.py
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Q, Count
from django.utils import timezone
from decimal import Decimal

from .models import (
    SupplierProfile, PaymentPreference, SourceOrder, SupplierInvoice,
    DeliveryRecord, WeighbridgeRecord, SupplierPayment, Notification
)
from .serializers import (
    SupplierProfileSerializer, PaymentPreferenceSerializer,
    SourceOrderSerializer, SourceOrderListSerializer,
    SupplierInvoiceSerializer, DeliveryRecordSerializer,
    WeighbridgeRecordSerializer, SupplierPaymentSerializer,
    NotificationSerializer, SupplierDashboardSerializer
)
from .permissions import IsSupplier, IsHubAdminOrBDM, IsSupplierOwner


class SupplierProfileViewSet(viewsets.ModelViewSet):
    """Manage supplier profiles"""
    queryset = SupplierProfile.objects.all()
    serializer_class = SupplierProfileSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['hub', 'is_verified']
    search_fields = ['business_name', 'user__phone_number', 'user__first_name', 'user__last_name']
    ordering_fields = ['created_at', 'business_name']
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter suppliers based on user role"""
        user = self.request.user
        
        if user.role in ['hub_admin', 'bdm', 'finance']:
            # Admins see all suppliers
            return SupplierProfile.objects.all()
        elif user.role == 'farmer':
            # Farmers only see their own profile
            return SupplierProfile.objects.filter(user=user)
        else:
            return SupplierProfile.objects.none()

    @action(detail=True, methods=['post'], permission_classes=[IsHubAdminOrBDM])
    def verify(self, request, pk=None):
        """Verify a supplier"""
        supplier = self.get_object()
        
        if supplier.is_verified:
            return Response(
                {"detail": "Supplier is already verified"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        supplier.is_verified = True
        supplier.verified_by = request.user
        supplier.verified_at = timezone.now()
        supplier.save()
        
        # Create notification
        Notification.objects.create(
            user=supplier.user,
            notification_type='source_order_status',
            title="Supplier Profile Verified",
            message=f"Your supplier profile has been verified by {request.user.get_full_name()}",
            related_object_type='supplier_profile',
            related_object_id=supplier.id
        )
        
        serializer = self.get_serializer(supplier)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's supplier profile"""
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            serializer = self.get_serializer(supplier)
            return Response(serializer.data)
        except SupplierProfile.DoesNotExist:
            return Response(
                {"detail": "No supplier profile found for this user"},
                status=status.HTTP_404_NOT_FOUND
            )


class PaymentPreferenceViewSet(viewsets.ModelViewSet):
    """Manage payment preferences for suppliers"""
    queryset = PaymentPreference.objects.all()
    serializer_class = PaymentPreferenceSerializer
    permission_classes = [IsAuthenticated, IsSupplierOwner]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['supplier', 'method', 'is_default', 'is_active']
    ordering = ['-is_default', '-created_at']

    def get_queryset(self):
        """Filter payment preferences based on user"""
        user = self.request.user
        
        if user.role in ['hub_admin', 'bdm', 'finance']:
            return PaymentPreference.objects.all()
        elif hasattr(user, 'supplier_profile'):
            return PaymentPreference.objects.filter(supplier=user.supplier_profile)
        else:
            return PaymentPreference.objects.none()


class SourceOrderViewSet(viewsets.ModelViewSet):
    """Manage source orders"""
    queryset = SourceOrder.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['supplier', 'hub', 'grain_type', 'status']
    search_fields = ['order_number', 'supplier__business_name']
    ordering_fields = ['created_at', 'expected_delivery_date', 'total_cost']
    ordering = ['-created_at']

    def get_serializer_class(self):
        """Use different serializers for list vs detail"""
        if self.action == 'list':
            return SourceOrderListSerializer
        return SourceOrderSerializer

    def get_queryset(self):
        """Filter orders based on user role"""
        user = self.request.user
        
        if user.role in ['hub_admin', 'bdm', 'finance']:
            # Admins see all orders
            return SourceOrder.objects.all()
        elif hasattr(user, 'supplier_profile'):
            # Suppliers see only their orders
            return SourceOrder.objects.filter(supplier=user.supplier_profile)
        else:
            return SourceOrder.objects.none()

    @action(detail=True, methods=['post'], permission_classes=[IsHubAdminOrBDM])
    def send_to_supplier(self, request, pk=None):
        """Send order to supplier"""
        order = self.get_object()
        
        if order.send_to_supplier():
            # Create notification
            Notification.objects.create(
                user=order.supplier.user,
                notification_type='source_order_created',
                title="New Purchase Order",
                message=f"You have received a new purchase order {order.order_number} for {order.quantity_kg}kg of {order.grain_type.name}",
                related_object_type='source_order',
                related_object_id=order.id
            )
            
            serializer = self.get_serializer(order)
            return Response(serializer.data)
        else:
            return Response(
                {"detail": "Order cannot be sent in current status"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], permission_classes=[IsSupplier])
    def accept(self, request, pk=None):
        """Supplier accepts the order"""
        order = self.get_object()
        
        # Verify supplier owns this order
        if order.supplier.user != request.user:
            return Response(
                {"detail": "You do not have permission to accept this order"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if order.accept_order():
            # Create notification for Bennu staff
            Notification.objects.create(
                user=order.created_by,
                notification_type='source_order_status',
                title="Order Accepted",
                message=f"Order {order.order_number} has been accepted by {order.supplier.business_name}",
                related_object_type='source_order',
                related_object_id=order.id
            )
            
            serializer = self.get_serializer(order)
            return Response(serializer.data)
        else:
            return Response(
                {"detail": "Order cannot be accepted in current status"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], permission_classes=[IsSupplier])
    def reject(self, request, pk=None):
        """Supplier rejects the order"""
        order = self.get_object()
        
        # Verify supplier owns this order
        if order.supplier.user != request.user:
            return Response(
                {"detail": "You do not have permission to reject this order"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if order.reject_order():
            # Create notification for Bennu staff
            Notification.objects.create(
                user=order.created_by,
                notification_type='source_order_status',
                title="Order Rejected",
                message=f"Order {order.order_number} has been rejected by {order.supplier.business_name}",
                related_object_type='source_order',
                related_object_id=order.id
            )
            
            serializer = self.get_serializer(order)
            return Response(serializer.data)
        else:
            return Response(
                {"detail": "Order cannot be rejected in current status"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def mark_in_transit(self, request, pk=None):
        """Mark order as in transit"""
        order = self.get_object()
        
        if order.mark_in_transit():
            # Update logistics info if provided
            if 'driver_name' in request.data:
                order.driver_name = request.data['driver_name']
            if 'driver_phone' in request.data:
                order.driver_phone = request.data['driver_phone']
            order.save()
            
            # Create notification
            Notification.objects.create(
                user=order.created_by,
                notification_type='source_order_status',
                title="Order In Transit",
                message=f"Order {order.order_number} is now in transit to {order.hub.name}",
                related_object_type='source_order',
                related_object_id=order.id
            )
            
            serializer = self.get_serializer(order)
            return Response(serializer.data)
        else:
            return Response(
                {"detail": "Order cannot be marked in transit in current status"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        """Get orders for current supplier"""
        if not hasattr(request.user, 'supplier_profile'):
            return Response(
                {"detail": "User is not a supplier"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        orders = SourceOrder.objects.filter(supplier=request.user.supplier_profile)
        
        # Apply status filter if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            orders = orders.filter(status=status_filter)
        
        serializer = SourceOrderListSerializer(orders, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get order statistics"""
        queryset = self.get_queryset()
        
        stats = {
            'total_orders': queryset.count(),
            'draft': queryset.filter(status='draft').count(),
            'open': queryset.filter(status='open').count(),
            'accepted': queryset.filter(status='accepted').count(),
            'in_transit': queryset.filter(status='in_transit').count(),
            'delivered': queryset.filter(status='delivered').count(),
            'completed': queryset.filter(status='completed').count(),
            'total_value': float(queryset.aggregate(total=Sum('total_cost'))['total'] or 0),
            'total_quantity_kg': float(queryset.aggregate(total=Sum('quantity_kg'))['total'] or 0),
        }
        
        return Response(stats)


class DeliveryRecordViewSet(viewsets.ModelViewSet):
    """Manage delivery records"""
    queryset = DeliveryRecord.objects.all()
    serializer_class = DeliveryRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['hub', 'source_order']
    ordering = ['-received_at']

    def get_queryset(self):
        """Filter deliveries based on user role"""
        user = self.request.user
        
        if user.role in ['hub_admin', 'bdm', 'finance']:
            return DeliveryRecord.objects.all()
        elif hasattr(user, 'supplier_profile'):
            return DeliveryRecord.objects.filter(source_order__supplier=user.supplier_profile)
        else:
            return DeliveryRecord.objects.none()


class WeighbridgeRecordViewSet(viewsets.ModelViewSet):
    """Manage weighbridge records"""
    queryset = WeighbridgeRecord.objects.all()
    serializer_class = WeighbridgeRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['source_order', 'quality_grade']
    ordering = ['-weighed_at']

    def get_queryset(self):
        """Filter weighbridge records based on user role"""
        user = self.request.user
        
        if user.role in ['hub_admin', 'bdm', 'finance']:
            return WeighbridgeRecord.objects.all()
        elif hasattr(user, 'supplier_profile'):
            return WeighbridgeRecord.objects.filter(source_order__supplier=user.supplier_profile)
        else:
            return WeighbridgeRecord.objects.none()


class SupplierInvoiceViewSet(viewsets.ModelViewSet):
    """Manage supplier invoices"""
    queryset = SupplierInvoice.objects.all()
    serializer_class = SupplierInvoiceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['supplier', 'status']
    search_fields = ['invoice_number', 'source_order__order_number']
    ordering = ['-issued_at']

    def get_queryset(self):
        """Filter invoices based on user role"""
        user = self.request.user
        
        if user.role in ['hub_admin', 'bdm', 'finance']:
            return SupplierInvoice.objects.all()
        elif hasattr(user, 'supplier_profile'):
            return SupplierInvoice.objects.filter(supplier=user.supplier_profile)
        else:
            return SupplierInvoice.objects.none()

    @action(detail=False, methods=['get'])
    def my_invoices(self, request):
        """Get invoices for current supplier"""
        if not hasattr(request.user, 'supplier_profile'):
            return Response(
                {"detail": "User is not a supplier"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invoices = SupplierInvoice.objects.filter(supplier=request.user.supplier_profile)
        
        # Apply status filter if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            invoices = invoices.filter(status=status_filter)
        
        serializer = self.get_serializer(invoices, many=True)
        return Response(serializer.data)


class SupplierPaymentViewSet(viewsets.ModelViewSet):
    """Manage supplier payments"""
    queryset = SupplierPayment.objects.all()
    serializer_class = SupplierPaymentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['supplier_invoice', 'status', 'method']
    search_fields = ['payment_number', 'reference_number']
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter payments based on user role"""
        user = self.request.user
        
        if user.role in ['hub_admin', 'bdm', 'finance']:
            return SupplierPayment.objects.all()
        elif hasattr(user, 'supplier_profile'):
            return SupplierPayment.objects.filter(
                supplier_invoice__supplier=user.supplier_profile
            )
        else:
            return SupplierPayment.objects.none()

    @action(detail=True, methods=['post'], permission_classes=[IsHubAdminOrBDM])
    def mark_completed(self, request, pk=None):
        """Mark payment as completed"""
        payment = self.get_object()
        
        if payment.status == 'completed':
            return Response(
                {"detail": "Payment is already completed"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payment.status = 'completed'
        payment.completed_at = timezone.now()
        payment.save()
        
        # Update invoice
        invoice = payment.supplier_invoice
        invoice.amount_paid += payment.amount
        invoice.update_payment_status()
        
        # Create notification for supplier
        Notification.objects.create(
            user=invoice.supplier.user,
            notification_type='payment_made',
            title="Payment Received",
            message=f"Payment of {payment.amount} UGX has been processed for invoice {invoice.invoice_number}",
            related_object_type='supplier_payment',
            related_object_id=payment.id
        )
        
        serializer = self.get_serializer(payment)
        return Response(serializer.data)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """Manage user notifications"""
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['notification_type', 'is_read']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get notifications for current user"""
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark notification as read"""
        notification = self.get_object()
        notification.mark_as_read()
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"detail": "All notifications marked as read"})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications"""
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread_count": count})


class SupplierDashboardViewSet(viewsets.ViewSet):
    """Dashboard data for suppliers"""
    permission_classes = [IsAuthenticated, IsSupplier]

    def list(self, request):
        """Get supplier dashboard data"""
        if not hasattr(request.user, 'supplier_profile'):
            return Response(
                {"detail": "User is not a supplier"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        supplier = request.user.supplier_profile
        
        # Order statistics
        all_orders = SourceOrder.objects.filter(supplier=supplier)
        completed_orders = all_orders.filter(status='completed')
        
        # Invoice statistics
        all_invoices = SupplierInvoice.objects.filter(supplier=supplier)
        
        # Calculate totals
        total_supplied = completed_orders.aggregate(total=Sum('quantity_kg'))['total'] or Decimal('0')
        total_earned = all_invoices.filter(status='paid').aggregate(total=Sum('amount_paid'))['total'] or Decimal('0')
        pending_payment = all_invoices.filter(status__in=['pending', 'partial']).aggregate(total=Sum('balance_due'))['total'] or Decimal('0')
        
        # Recent items
        recent_orders = all_orders[:5]
        recent_invoices = all_invoices[:5]
        
        # Unread notifications
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        
        dashboard_data = {
            'total_orders': all_orders.count(),
            'pending_orders': all_orders.filter(status__in=['open', 'accepted', 'in_transit']).count(),
            'completed_orders': completed_orders.count(),
            'total_supplied_kg': total_supplied,
            'total_earned': total_earned,
            'pending_payment': pending_payment,
            'recent_orders': SourceOrderListSerializer(recent_orders, many=True).data,
            'recent_invoices': SupplierInvoiceSerializer(recent_invoices, many=True).data,
            'unread_notifications': unread_count,
        }
        
        serializer = SupplierDashboardSerializer(dashboard_data)
        return Response(serializer.data)