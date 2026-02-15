# sourcing/views.py
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum
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
from .permissions import (
    IsStaff, IsSupplier, IsStaffOrSupplier,
    IsHubAdminOrBDM, IsSupplierOwner,
    IsSupplierOrderOwner, CanManageSourceOrder,
)

STAFF_ROLES = ['super_admin', 'hub_admin', 'bdm', 'finance']


# ---------------------------------------------------------------------------
# Supplier Profile
# ---------------------------------------------------------------------------

class SupplierProfileViewSet(viewsets.ModelViewSet):
    """
    Manage supplier profiles.

    Permission matrix:
      list             → staff only
      create           → any authenticated user (farmer self-register or staff)
      retrieve         → staff OR the owning supplier (object-level)
      update           → staff OR the owning supplier (object-level)
      destroy          → staff only
      verify           → hub_admin / bdm / finance only
      me               → supplier only
    """
    queryset = SupplierProfile.objects.all()
    serializer_class = SupplierProfileSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['hub', 'is_verified']
    search_fields = ['business_name', 'user__phone_number', 'user__first_name', 'user__last_name']
    ordering_fields = ['created_at', 'business_name']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ['list', 'destroy']:
            permission_classes = [IsAuthenticated, IsStaff]

        elif self.action == 'create':
            # Open to authenticated users; serializer validate() blocks duplicates.
            permission_classes = [IsAuthenticated]

        elif self.action in ['retrieve', 'update', 'partial_update']:
            # IsSupplierOwner.has_object_permission limits suppliers to own record.
            permission_classes = [IsAuthenticated, IsSupplierOwner]

        elif self.action == 'verify':
            permission_classes = [IsAuthenticated, IsHubAdminOrBDM]

        elif self.action == 'me':
            permission_classes = [IsAuthenticated, IsSupplier]

        else:
            permission_classes = [IsAuthenticated]

        return [p() for p in permission_classes]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return SupplierProfile.objects.none()

        user = self.request.user

        if user.role in STAFF_ROLES:
            return SupplierProfile.objects.all()
        elif hasattr(user, 'supplier_profile'):
            # Suppliers only ever see their own record in the queryset
            return SupplierProfile.objects.filter(user=user)
        return SupplierProfile.objects.none()

    def perform_create(self, serializer):
        """
        Staff pass an explicit user_id. Farmers self-register without one —
        request.user is injected automatically. The serializer's validate()
        catches duplicates for both paths before hitting the DB.
        """
        if 'user' not in serializer.validated_data:
            serializer.save(user=self.request.user)
        else:
            serializer.save()

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Mark a supplier as verified. Staff only (enforced by get_permissions)."""
        supplier = self.get_object()

        if supplier.is_verified:
            return Response(
                {"detail": "Supplier is already verified."},
                status=status.HTTP_400_BAD_REQUEST
            )

        supplier.is_verified = True
        supplier.verified_by = request.user
        supplier.verified_at = timezone.now()
        supplier.save()

        Notification.objects.create(
            user=supplier.user,
            notification_type='source_order_status',
            title="Supplier Profile Verified",
            message=f"Your supplier profile has been verified by {request.user.get_full_name()}.",
            related_object_type='supplier_profile',
            related_object_id=supplier.id
        )

        return Response(self.get_serializer(supplier).data)

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Return the calling user's own supplier profile."""
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            return Response(self.get_serializer(supplier).data)
        except SupplierProfile.DoesNotExist:
            return Response(
                {"detail": "No supplier profile found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )


# ---------------------------------------------------------------------------
# Payment Preferences
# ---------------------------------------------------------------------------

class PaymentPreferenceViewSet(viewsets.ModelViewSet):
    """
    Manage payment preferences.

    Permission matrix:
      list, retrieve          → staff OR owning supplier
      create, update, destroy → staff OR owning supplier
                                (object-level IsSupplierOwner blocks cross-supplier writes)
    """
    queryset = PaymentPreference.objects.all()
    serializer_class = PaymentPreferenceSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['supplier', 'method', 'is_default', 'is_active']
    ordering = ['-is_default', '-created_at']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAuthenticated, IsStaffOrSupplier]
        else:
            # create / update / partial_update / destroy
            # IsSupplierOwner.has_object_permission prevents cross-supplier writes
            permission_classes = [IsAuthenticated, IsStaffOrSupplier, IsSupplierOwner]
        return [p() for p in permission_classes]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return PaymentPreference.objects.none()

        user = self.request.user

        if user.role in STAFF_ROLES:
            return PaymentPreference.objects.all()
        elif hasattr(user, 'supplier_profile'):
            return PaymentPreference.objects.filter(supplier=user.supplier_profile)
        return PaymentPreference.objects.none()


# ---------------------------------------------------------------------------
# Source Orders
# ---------------------------------------------------------------------------

class SourceOrderViewSet(viewsets.ModelViewSet):
    """
    Manage source / purchase orders.

    Permission matrix:
      list             → staff OR supplier (suppliers see own only via queryset)
      create           → staff only
      retrieve         → staff OR owning supplier (object-level)
      update           → staff only
      destroy          → staff only
      send_to_supplier → hub_admin / bdm / finance only
      accept           → owning supplier only
      reject           → owning supplier only
      mark_in_transit  → staff only  ← was unguarded before this patch
      my_orders        → supplier only
      stats            → staff only
    """
    queryset = SourceOrder.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['supplier', 'hub', 'grain_type', 'status']
    search_fields = ['order_number', 'supplier__business_name']
    ordering_fields = ['created_at', 'expected_delivery_date', 'total_cost']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return SourceOrderListSerializer
        return SourceOrderSerializer

    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [IsAuthenticated, IsStaff]

        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [IsAuthenticated, IsStaff]

        elif self.action == 'retrieve':
            # IsSupplierOrderOwner limits suppliers to their own order
            permission_classes = [IsAuthenticated, IsSupplierOrderOwner]

        elif self.action == 'list':
            permission_classes = [IsAuthenticated, IsStaffOrSupplier]

        elif self.action == 'send_to_supplier':
            permission_classes = [IsAuthenticated, IsHubAdminOrBDM]

        elif self.action in ['accept', 'reject']:
            permission_classes = [IsAuthenticated, IsSupplier]

        elif self.action == 'mark_in_transit':
            # Logistics is a staff action; suppliers must not self-dispatch
            permission_classes = [IsAuthenticated, IsStaff]

        elif self.action == 'my_orders':
            permission_classes = [IsAuthenticated, IsSupplier]

        elif self.action == 'stats':
            permission_classes = [IsAuthenticated, IsStaff]

        else:
            permission_classes = [IsAuthenticated]

        return [p() for p in permission_classes]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return SourceOrder.objects.none()

        user = self.request.user

        if user.role in STAFF_ROLES:
            return SourceOrder.objects.all()
        elif hasattr(user, 'supplier_profile'):
            return SourceOrder.objects.filter(supplier=user.supplier_profile)
        return SourceOrder.objects.none()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def send_to_supplier(self, request, pk=None):
        """Send a draft order to the supplier. Staff only."""
        order = self.get_object()

        if order.send_to_supplier():
            Notification.objects.create(
                user=order.supplier.user,
                notification_type='source_order_created',
                title="New Purchase Order",
                message=(
                    f"You have received a new purchase order {order.order_number} "
                    f"for {order.quantity_kg}kg of {order.grain_type.name}."
                ),
                related_object_type='source_order',
                related_object_id=order.id
            )
            return Response(self.get_serializer(order).data)

        return Response(
            {"detail": "Order cannot be sent in its current status."},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Supplier accepts the order. Supplier only."""
        order = self.get_object()

        if order.supplier.user != request.user:
            return Response(
                {"detail": "You do not have permission to accept this order."},
                status=status.HTTP_403_FORBIDDEN
            )

        if order.accept_order():
            Notification.objects.create(
                user=order.created_by,
                notification_type='source_order_status',
                title="Order Accepted",
                message=(
                    f"Order {order.order_number} has been accepted by "
                    f"{order.supplier.business_name}."
                ),
                related_object_type='source_order',
                related_object_id=order.id
            )
            return Response(self.get_serializer(order).data)

        return Response(
            {"detail": "Order cannot be accepted in its current status."},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Supplier rejects the order. Supplier only."""
        order = self.get_object()

        if order.supplier.user != request.user:
            return Response(
                {"detail": "You do not have permission to reject this order."},
                status=status.HTTP_403_FORBIDDEN
            )

        if order.reject_order():
            Notification.objects.create(
                user=order.created_by,
                notification_type='source_order_status',
                title="Order Rejected",
                message=(
                    f"Order {order.order_number} has been rejected by "
                    f"{order.supplier.business_name}."
                ),
                related_object_type='source_order',
                related_object_id=order.id
            )
            return Response(self.get_serializer(order).data)

        return Response(
            {"detail": "Order cannot be rejected in its current status."},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=True, methods=['post'])
    def mark_in_transit(self, request, pk=None):
        """Mark order as in transit. Staff only."""
        order = self.get_object()

        if order.mark_in_transit():
            if 'driver_name' in request.data:
                order.driver_name = request.data['driver_name']
            if 'driver_phone' in request.data:
                order.driver_phone = request.data['driver_phone']
            order.save()

            Notification.objects.create(
                user=order.supplier.user,
                notification_type='source_order_status',
                title="Order In Transit",
                message=(
                    f"Your grain for order {order.order_number} is now in transit "
                    f"to {order.hub.name}."
                ),
                related_object_type='source_order',
                related_object_id=order.id
            )
            return Response(self.get_serializer(order).data)

        return Response(
            {"detail": "Order cannot be marked in transit in its current status."},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        """Return orders belonging to the calling supplier."""
        orders = SourceOrder.objects.filter(supplier=request.user.supplier_profile)

        status_filter = request.query_params.get('status')
        if status_filter:
            orders = orders.filter(status=status_filter)

        return Response(SourceOrderListSerializer(orders, many=True).data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Aggregate order statistics. Staff only."""
        queryset = self.get_queryset()

        return Response({
            'total_orders': queryset.count(),
            'draft': queryset.filter(status='draft').count(),
            'open': queryset.filter(status='open').count(),
            'accepted': queryset.filter(status='accepted').count(),
            'in_transit': queryset.filter(status='in_transit').count(),
            'delivered': queryset.filter(status='delivered').count(),
            'completed': queryset.filter(status='completed').count(),
            'total_value': float(queryset.aggregate(total=Sum('total_cost'))['total'] or 0),
            'total_quantity_kg': float(queryset.aggregate(total=Sum('quantity_kg'))['total'] or 0),
        })


# ---------------------------------------------------------------------------
# Delivery Records
# ---------------------------------------------------------------------------

class DeliveryRecordViewSet(viewsets.ModelViewSet):
    """
    Manage delivery records.

    Permission matrix:
      list, retrieve  → staff OR owning supplier (read-only for supplier)
      create          → staff only  (hub staff record arrivals)
      update, destroy → staff only
    """
    queryset = DeliveryRecord.objects.all()
    serializer_class = DeliveryRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['hub', 'source_order']
    ordering = ['-received_at']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAuthenticated, IsStaffOrSupplier]
        else:
            permission_classes = [IsAuthenticated, IsStaff]
        return [p() for p in permission_classes]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return DeliveryRecord.objects.none()

        user = self.request.user

        if user.role in STAFF_ROLES:
            return DeliveryRecord.objects.all()
        elif hasattr(user, 'supplier_profile'):
            return DeliveryRecord.objects.filter(
                source_order__supplier=user.supplier_profile
            )
        return DeliveryRecord.objects.none()


# ---------------------------------------------------------------------------
# Weighbridge Records
# ---------------------------------------------------------------------------

class WeighbridgeRecordViewSet(viewsets.ModelViewSet):
    """
    Manage weighbridge / quality-check records.

    Permission matrix:
      list, retrieve  → staff OR owning supplier (read-only for supplier)
      create          → staff only  (hub staff weigh the grain)
      update, destroy → staff only
    """
    queryset = WeighbridgeRecord.objects.all()
    serializer_class = WeighbridgeRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['source_order', 'quality_grade']
    ordering = ['-weighed_at']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAuthenticated, IsStaffOrSupplier]
        else:
            permission_classes = [IsAuthenticated, IsStaff]
        return [p() for p in permission_classes]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return WeighbridgeRecord.objects.none()

        user = self.request.user

        if user.role in STAFF_ROLES:
            return WeighbridgeRecord.objects.all()
        elif hasattr(user, 'supplier_profile'):
            return WeighbridgeRecord.objects.filter(
                source_order__supplier=user.supplier_profile
            )
        return WeighbridgeRecord.objects.none()


# ---------------------------------------------------------------------------
# Supplier Invoices
# ---------------------------------------------------------------------------

class SupplierInvoiceViewSet(viewsets.ModelViewSet):
    """
    Manage supplier invoices.

    Invoices are system-generated via signals; manual creation is blocked.

    Permission matrix:
      list, retrieve  → staff OR owning supplier
      create          → staff only (and should generally be avoided — use signals)
      update          → staff only (e.g. adding notes or adjusting due_date)
      destroy         → staff only
      my_invoices     → supplier only
    """
    queryset = SupplierInvoice.objects.all()
    serializer_class = SupplierInvoiceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['supplier', 'status']
    search_fields = ['invoice_number', 'source_order__order_number']
    ordering = ['-issued_at']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAuthenticated, IsStaffOrSupplier]

        elif self.action == 'my_invoices':
            permission_classes = [IsAuthenticated, IsSupplier]

        else:
            # create / update / partial_update / destroy
            permission_classes = [IsAuthenticated, IsStaff]

        return [p() for p in permission_classes]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return SupplierInvoice.objects.none()

        user = self.request.user

        if user.role in STAFF_ROLES:
            return SupplierInvoice.objects.all()
        elif hasattr(user, 'supplier_profile'):
            return SupplierInvoice.objects.filter(supplier=user.supplier_profile)
        return SupplierInvoice.objects.none()

    @action(detail=False, methods=['get'])
    def my_invoices(self, request):
        """Return invoices for the calling supplier."""
        invoices = SupplierInvoice.objects.filter(
            supplier=request.user.supplier_profile
        )

        status_filter = request.query_params.get('status')
        if status_filter:
            invoices = invoices.filter(status=status_filter)

        return Response(self.get_serializer(invoices, many=True).data)


# ---------------------------------------------------------------------------
# Supplier Payments
# ---------------------------------------------------------------------------

class SupplierPaymentViewSet(viewsets.ModelViewSet):
    """
    Manage supplier payments.

    Permission matrix:
      list, retrieve  → staff OR owning supplier (read-only for supplier)
      create          → staff only  (finance initiates payments)
      update, destroy → staff only
      mark_completed  → hub_admin / bdm / finance only
    """
    queryset = SupplierPayment.objects.all()
    serializer_class = SupplierPaymentSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['supplier_invoice', 'status', 'method']
    search_fields = ['payment_number', 'reference_number']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAuthenticated, IsStaffOrSupplier]

        elif self.action == 'mark_completed':
            permission_classes = [IsAuthenticated, IsHubAdminOrBDM]

        else:
            # create / update / partial_update / destroy
            permission_classes = [IsAuthenticated, IsStaff]

        return [p() for p in permission_classes]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return SupplierPayment.objects.none()

        user = self.request.user

        if user.role in STAFF_ROLES:
            return SupplierPayment.objects.all()
        elif hasattr(user, 'supplier_profile'):
            return SupplierPayment.objects.filter(
                supplier_invoice__supplier=user.supplier_profile
            )
        return SupplierPayment.objects.none()

    @action(detail=True, methods=['post'])
    def mark_completed(self, request, pk=None):
        """Mark a payment as completed and update the invoice. Staff only."""
        payment = self.get_object()

        if payment.status == 'completed':
            return Response(
                {"detail": "Payment is already completed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment.status = 'completed'
        payment.completed_at = timezone.now()
        payment.save()

        invoice = payment.supplier_invoice
        invoice.amount_paid += payment.amount
        invoice.update_payment_status()

        Notification.objects.create(
            user=invoice.supplier.user,
            notification_type='payment_made',
            title="Payment Received",
            message=(
                f"Payment of {payment.amount} UGX has been processed for "
                f"invoice {invoice.invoice_number}."
            ),
            related_object_type='supplier_payment',
            related_object_id=payment.id
        )

        return Response(self.get_serializer(payment).data)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only notification feed for the authenticated user.
    Every user only ever sees their own notifications (enforced in get_queryset).
    No role restriction needed — the queryset is always scoped to request.user.
    """
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['notification_type', 'is_read']
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_as_read()
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"detail": "All notifications marked as read."})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread_count": count})


# ---------------------------------------------------------------------------
# Supplier Dashboard
# ---------------------------------------------------------------------------

class SupplierDashboardViewSet(viewsets.ViewSet):
    """
    Aggregated dashboard for the calling supplier.
    Supplier only — staff should use dedicated reporting endpoints.
    """
    permission_classes = [IsAuthenticated, IsSupplier]

    def list(self, request):
        supplier = request.user.supplier_profile

        all_orders = SourceOrder.objects.filter(supplier=supplier)
        completed_orders = all_orders.filter(status='completed')
        all_invoices = SupplierInvoice.objects.filter(supplier=supplier)

        total_supplied = (
            completed_orders.aggregate(total=Sum('quantity_kg'))['total']
            or Decimal('0')
        )
        total_earned = (
            all_invoices.filter(status='paid')
            .aggregate(total=Sum('amount_paid'))['total']
            or Decimal('0')
        )
        pending_payment = (
            all_invoices.filter(status__in=['pending', 'partial'])
            .aggregate(total=Sum('balance_due'))['total']
            or Decimal('0')
        )

        dashboard_data = {
            'total_orders': all_orders.count(),
            'pending_orders': all_orders.filter(
                status__in=['open', 'accepted', 'in_transit']
            ).count(),
            'completed_orders': completed_orders.count(),
            'total_supplied_kg': total_supplied,
            'total_earned': total_earned,
            'pending_payment': pending_payment,
            'recent_orders': SourceOrderListSerializer(all_orders[:5], many=True).data,
            'recent_invoices': SupplierInvoiceSerializer(all_invoices[:5], many=True).data,
            'unread_notifications': Notification.objects.filter(
                user=request.user, is_read=False
            ).count(),
        }

        return Response(SupplierDashboardSerializer(dashboard_data).data)









# # sourcing/views.py
# from rest_framework import viewsets, status, filters
# from rest_framework.decorators import action
# from rest_framework.response import Response
# from rest_framework.permissions import IsAuthenticated
# from django_filters.rest_framework import DjangoFilterBackend
# from django.db.models import Sum, Q, Count
# from django.utils import timezone
# from decimal import Decimal

# from .models import (
#     SupplierProfile, PaymentPreference, SourceOrder, SupplierInvoice,
#     DeliveryRecord, WeighbridgeRecord, SupplierPayment, Notification
# )
# from .serializers import (
#     SupplierProfileSerializer, PaymentPreferenceSerializer,
#     SourceOrderSerializer, SourceOrderListSerializer,
#     SupplierInvoiceSerializer, DeliveryRecordSerializer,
#     WeighbridgeRecordSerializer, SupplierPaymentSerializer,
#     NotificationSerializer, SupplierDashboardSerializer
# )
# from .permissions import IsSupplier, IsHubAdminOrBDM, IsSupplierOwner

# STAFF_ROLES = ['super_admin', 'hub_admin', 'bdm', 'finance']


# class SupplierProfileViewSet(viewsets.ModelViewSet):
#     """Manage supplier profiles"""
#     queryset = SupplierProfile.objects.all()
#     serializer_class = SupplierProfileSerializer
#     permission_classes = [IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
#     filterset_fields = ['hub', 'is_verified']
#     search_fields = ['business_name', 'user__phone_number', 'user__first_name', 'user__last_name']
#     ordering_fields = ['created_at', 'business_name']
#     ordering = ['-created_at']

#     def get_queryset(self):
#         """Filter suppliers based on user role"""
#         if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
#             return SupplierProfile.objects.none()

#         user = self.request.user

#         if user.role in STAFF_ROLES:
#             return SupplierProfile.objects.all()
#         elif user.role == 'farmer':
#             return SupplierProfile.objects.filter(user=user)
#         else:
#             return SupplierProfile.objects.none()

#     def perform_create(self, serializer):
#         """
#         FIX: The duplicate-profile check now lives entirely in the serializer's
#         validate() method, which runs before this method is ever reached.
#         This means both the explicit-user_id path (staff creating for another
#         user) and the auto-assign path (farmer self-registering) are caught
#         cleanly at validation time, returning a 400 instead of a DB 500.

#         The only responsibility here is to inject request.user when no user_id
#         was provided in the payload.

#         Root cause of the original bug:
#           user_id is declared with source='user' on the serializer field, so
#           DRF stores it in validated_data under the key 'user', NOT 'user_id'.
#           The old check `'user' not in serializer.validated_data` was therefore
#           always False when user_id was present in the request, so the duplicate
#           guard was silently skipped and save() was called unconditionally,
#           letting the DB raise an IntegrityError 500.
#         """
#         if 'user' not in serializer.validated_data:
#             # Auto-assign path: no user_id in payload, use the requesting user.
#             # Duplicate check for this case is handled in serializer.validate()
#             # via the request context fallback.
#             serializer.save(user=self.request.user)
#         else:
#             # Explicit user_id path: duplicate check already passed in validate().
#             serializer.save()

#     @action(detail=True, methods=['post'], permission_classes=[IsHubAdminOrBDM])
#     def verify(self, request, pk=None):
#         """Verify a supplier"""
#         supplier = self.get_object()

#         if supplier.is_verified:
#             return Response(
#                 {"detail": "Supplier is already verified"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         supplier.is_verified = True
#         supplier.verified_by = request.user
#         supplier.verified_at = timezone.now()
#         supplier.save()

#         # Create notification
#         Notification.objects.create(
#             user=supplier.user,
#             notification_type='source_order_status',
#             title="Supplier Profile Verified",
#             message=f"Your supplier profile has been verified by {request.user.get_full_name()}",
#             related_object_type='supplier_profile',
#             related_object_id=supplier.id
#         )

#         serializer = self.get_serializer(supplier)
#         return Response(serializer.data)

#     @action(detail=False, methods=['get'])
#     def me(self, request):
#         """Get current user's supplier profile"""
#         try:
#             supplier = SupplierProfile.objects.get(user=request.user)
#             serializer = self.get_serializer(supplier)
#             return Response(serializer.data)
#         except SupplierProfile.DoesNotExist:
#             return Response(
#                 {"detail": "No supplier profile found for this user"},
#                 status=status.HTTP_404_NOT_FOUND
#             )


# class PaymentPreferenceViewSet(viewsets.ModelViewSet):
#     """Manage payment preferences for suppliers"""
#     queryset = PaymentPreference.objects.all()
#     serializer_class = PaymentPreferenceSerializer
#     permission_classes = [IsAuthenticated, IsSupplierOwner]
#     filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
#     filterset_fields = ['supplier', 'method', 'is_default', 'is_active']
#     ordering = ['-is_default', '-created_at']

#     def get_queryset(self):
#         """Filter payment preferences based on user"""
#         if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
#             return PaymentPreference.objects.none()

#         user = self.request.user

#         if user.role in STAFF_ROLES:
#             return PaymentPreference.objects.all()
#         elif hasattr(user, 'supplier_profile'):
#             return PaymentPreference.objects.filter(supplier=user.supplier_profile)
#         else:
#             return PaymentPreference.objects.none()


# class SourceOrderViewSet(viewsets.ModelViewSet):
#     """Manage source orders"""
#     queryset = SourceOrder.objects.all()
#     permission_classes = [IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
#     filterset_fields = ['supplier', 'hub', 'grain_type', 'status']
#     search_fields = ['order_number', 'supplier__business_name']
#     ordering_fields = ['created_at', 'expected_delivery_date', 'total_cost']
#     ordering = ['-created_at']

#     def get_serializer_class(self):
#         """Use different serializers for list vs detail"""
#         if self.action == 'list':
#             return SourceOrderListSerializer
#         return SourceOrderSerializer

#     def get_queryset(self):
#         """Filter orders based on user role"""
#         if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
#             return SourceOrder.objects.none()

#         user = self.request.user

#         if user.role in STAFF_ROLES:
#             return SourceOrder.objects.all()
#         elif hasattr(user, 'supplier_profile'):
#             return SourceOrder.objects.filter(supplier=user.supplier_profile)
#         else:
#             return SourceOrder.objects.none()

#     @action(detail=True, methods=['post'], permission_classes=[IsHubAdminOrBDM])
#     def send_to_supplier(self, request, pk=None):
#         """Send order to supplier"""
#         order = self.get_object()

#         if order.send_to_supplier():
#             # Create notification
#             Notification.objects.create(
#                 user=order.supplier.user,
#                 notification_type='source_order_created',
#                 title="New Purchase Order",
#                 message=f"You have received a new purchase order {order.order_number} for {order.quantity_kg}kg of {order.grain_type.name}",
#                 related_object_type='source_order',
#                 related_object_id=order.id
#             )

#             serializer = self.get_serializer(order)
#             return Response(serializer.data)
#         else:
#             return Response(
#                 {"detail": "Order cannot be sent in current status"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#     @action(detail=True, methods=['post'], permission_classes=[IsSupplier])
#     def accept(self, request, pk=None):
#         """Supplier accepts the order"""
#         order = self.get_object()

#         # Verify supplier owns this order
#         if order.supplier.user != request.user:
#             return Response(
#                 {"detail": "You do not have permission to accept this order"},
#                 status=status.HTTP_403_FORBIDDEN
#             )

#         if order.accept_order():
#             # Create notification for Bennu staff
#             Notification.objects.create(
#                 user=order.created_by,
#                 notification_type='source_order_status',
#                 title="Order Accepted",
#                 message=f"Order {order.order_number} has been accepted by {order.supplier.business_name}",
#                 related_object_type='source_order',
#                 related_object_id=order.id
#             )

#             serializer = self.get_serializer(order)
#             return Response(serializer.data)
#         else:
#             return Response(
#                 {"detail": "Order cannot be accepted in current status"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#     @action(detail=True, methods=['post'], permission_classes=[IsSupplier])
#     def reject(self, request, pk=None):
#         """Supplier rejects the order"""
#         order = self.get_object()

#         # Verify supplier owns this order
#         if order.supplier.user != request.user:
#             return Response(
#                 {"detail": "You do not have permission to reject this order"},
#                 status=status.HTTP_403_FORBIDDEN
#             )

#         if order.reject_order():
#             # Create notification for Bennu staff
#             Notification.objects.create(
#                 user=order.created_by,
#                 notification_type='source_order_status',
#                 title="Order Rejected",
#                 message=f"Order {order.order_number} has been rejected by {order.supplier.business_name}",
#                 related_object_type='source_order',
#                 related_object_id=order.id
#             )

#             serializer = self.get_serializer(order)
#             return Response(serializer.data)
#         else:
#             return Response(
#                 {"detail": "Order cannot be rejected in current status"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#     @action(detail=True, methods=['post'])
#     def mark_in_transit(self, request, pk=None):
#         """Mark order as in transit"""
#         order = self.get_object()

#         if order.mark_in_transit():
#             # Update logistics info if provided
#             if 'driver_name' in request.data:
#                 order.driver_name = request.data['driver_name']
#             if 'driver_phone' in request.data:
#                 order.driver_phone = request.data['driver_phone']
#             order.save()

#             # Create notification
#             Notification.objects.create(
#                 user=order.created_by,
#                 notification_type='source_order_status',
#                 title="Order In Transit",
#                 message=f"Order {order.order_number} is now in transit to {order.hub.name}",
#                 related_object_type='source_order',
#                 related_object_id=order.id
#             )

#             serializer = self.get_serializer(order)
#             return Response(serializer.data)
#         else:
#             return Response(
#                 {"detail": "Order cannot be marked in transit in current status"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#     @action(detail=False, methods=['get'])
#     def my_orders(self, request):
#         """Get orders for current supplier"""
#         if not hasattr(request.user, 'supplier_profile'):
#             return Response(
#                 {"detail": "User is not a supplier"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         orders = SourceOrder.objects.filter(supplier=request.user.supplier_profile)

#         # Apply status filter if provided
#         status_filter = request.query_params.get('status')
#         if status_filter:
#             orders = orders.filter(status=status_filter)

#         serializer = SourceOrderListSerializer(orders, many=True)
#         return Response(serializer.data)

#     @action(detail=False, methods=['get'])
#     def stats(self, request):
#         """Get order statistics"""
#         queryset = self.get_queryset()

#         stats = {
#             'total_orders': queryset.count(),
#             'draft': queryset.filter(status='draft').count(),
#             'open': queryset.filter(status='open').count(),
#             'accepted': queryset.filter(status='accepted').count(),
#             'in_transit': queryset.filter(status='in_transit').count(),
#             'delivered': queryset.filter(status='delivered').count(),
#             'completed': queryset.filter(status='completed').count(),
#             'total_value': float(queryset.aggregate(total=Sum('total_cost'))['total'] or 0),
#             'total_quantity_kg': float(queryset.aggregate(total=Sum('quantity_kg'))['total'] or 0),
#         }

#         return Response(stats)


# class DeliveryRecordViewSet(viewsets.ModelViewSet):
#     """Manage delivery records"""
#     queryset = DeliveryRecord.objects.all()
#     serializer_class = DeliveryRecordSerializer
#     permission_classes = [IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
#     filterset_fields = ['hub', 'source_order']
#     ordering = ['-received_at']

#     def get_queryset(self):
#         """Filter deliveries based on user role"""
#         if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
#             return DeliveryRecord.objects.none()

#         user = self.request.user

#         if user.role in STAFF_ROLES:
#             return DeliveryRecord.objects.all()
#         elif hasattr(user, 'supplier_profile'):
#             return DeliveryRecord.objects.filter(source_order__supplier=user.supplier_profile)
#         else:
#             return DeliveryRecord.objects.none()


# class WeighbridgeRecordViewSet(viewsets.ModelViewSet):
#     """Manage weighbridge records"""
#     queryset = WeighbridgeRecord.objects.all()
#     serializer_class = WeighbridgeRecordSerializer
#     permission_classes = [IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
#     filterset_fields = ['source_order', 'quality_grade']
#     ordering = ['-weighed_at']

#     def get_queryset(self):
#         """Filter weighbridge records based on user role"""
#         if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
#             return WeighbridgeRecord.objects.none()

#         user = self.request.user

#         if user.role in STAFF_ROLES:
#             return WeighbridgeRecord.objects.all()
#         elif hasattr(user, 'supplier_profile'):
#             return WeighbridgeRecord.objects.filter(source_order__supplier=user.supplier_profile)
#         else:
#             return WeighbridgeRecord.objects.none()


# class SupplierInvoiceViewSet(viewsets.ModelViewSet):
#     """Manage supplier invoices"""
#     queryset = SupplierInvoice.objects.all()
#     serializer_class = SupplierInvoiceSerializer
#     permission_classes = [IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
#     filterset_fields = ['supplier', 'status']
#     search_fields = ['invoice_number', 'source_order__order_number']
#     ordering = ['-issued_at']

#     def get_queryset(self):
#         """Filter invoices based on user role"""
#         if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
#             return SupplierInvoice.objects.none()

#         user = self.request.user

#         if user.role in STAFF_ROLES:
#             return SupplierInvoice.objects.all()
#         elif hasattr(user, 'supplier_profile'):
#             return SupplierInvoice.objects.filter(supplier=user.supplier_profile)
#         else:
#             return SupplierInvoice.objects.none()

#     @action(detail=False, methods=['get'])
#     def my_invoices(self, request):
#         """Get invoices for current supplier"""
#         if not hasattr(request.user, 'supplier_profile'):
#             return Response(
#                 {"detail": "User is not a supplier"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         invoices = SupplierInvoice.objects.filter(supplier=request.user.supplier_profile)

#         # Apply status filter if provided
#         status_filter = request.query_params.get('status')
#         if status_filter:
#             invoices = invoices.filter(status=status_filter)

#         serializer = self.get_serializer(invoices, many=True)
#         return Response(serializer.data)


# class SupplierPaymentViewSet(viewsets.ModelViewSet):
#     """Manage supplier payments"""
#     queryset = SupplierPayment.objects.all()
#     serializer_class = SupplierPaymentSerializer
#     permission_classes = [IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
#     filterset_fields = ['supplier_invoice', 'status', 'method']
#     search_fields = ['payment_number', 'reference_number']
#     ordering = ['-created_at']

#     def get_queryset(self):
#         """Filter payments based on user role"""
#         if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
#             return SupplierPayment.objects.none()

#         user = self.request.user

#         if user.role in STAFF_ROLES:
#             return SupplierPayment.objects.all()
#         elif hasattr(user, 'supplier_profile'):
#             return SupplierPayment.objects.filter(
#                 supplier_invoice__supplier=user.supplier_profile
#             )
#         else:
#             return SupplierPayment.objects.none()

#     @action(detail=True, methods=['post'], permission_classes=[IsHubAdminOrBDM])
#     def mark_completed(self, request, pk=None):
#         """Mark payment as completed"""
#         payment = self.get_object()

#         if payment.status == 'completed':
#             return Response(
#                 {"detail": "Payment is already completed"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         payment.status = 'completed'
#         payment.completed_at = timezone.now()
#         payment.save()

#         # Update invoice
#         invoice = payment.supplier_invoice
#         invoice.amount_paid += payment.amount
#         invoice.update_payment_status()

#         # Create notification for supplier
#         Notification.objects.create(
#             user=invoice.supplier.user,
#             notification_type='payment_made',
#             title="Payment Received",
#             message=f"Payment of {payment.amount} UGX has been processed for invoice {invoice.invoice_number}",
#             related_object_type='supplier_payment',
#             related_object_id=payment.id
#         )

#         serializer = self.get_serializer(payment)
#         return Response(serializer.data)


# class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
#     """Manage user notifications"""
#     queryset = Notification.objects.all()
#     serializer_class = NotificationSerializer
#     permission_classes = [IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
#     filterset_fields = ['notification_type', 'is_read']
#     ordering = ['-created_at']

#     def get_queryset(self):
#         """Get notifications for current user"""
#         if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
#             return Notification.objects.none()

#         return Notification.objects.filter(user=self.request.user)

#     @action(detail=True, methods=['post'])
#     def mark_read(self, request, pk=None):
#         """Mark notification as read"""
#         notification = self.get_object()
#         notification.mark_as_read()
#         serializer = self.get_serializer(notification)
#         return Response(serializer.data)

#     @action(detail=False, methods=['post'])
#     def mark_all_read(self, request):
#         """Mark all notifications as read"""
#         Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
#         return Response({"detail": "All notifications marked as read"})

#     @action(detail=False, methods=['get'])
#     def unread_count(self, request):
#         """Get count of unread notifications"""
#         count = Notification.objects.filter(user=request.user, is_read=False).count()
#         return Response({"unread_count": count})


# class SupplierDashboardViewSet(viewsets.ViewSet):
#     """Dashboard data for suppliers"""
#     permission_classes = [IsAuthenticated, IsSupplier]

#     def list(self, request):
#         """Get supplier dashboard data"""
#         if not hasattr(request.user, 'supplier_profile'):
#             return Response(
#                 {"detail": "User is not a supplier"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         supplier = request.user.supplier_profile

#         # Order statistics
#         all_orders = SourceOrder.objects.filter(supplier=supplier)
#         completed_orders = all_orders.filter(status='completed')

#         # Invoice statistics
#         all_invoices = SupplierInvoice.objects.filter(supplier=supplier)

#         # Calculate totals
#         total_supplied = completed_orders.aggregate(total=Sum('quantity_kg'))['total'] or Decimal('0')
#         total_earned = all_invoices.filter(status='paid').aggregate(total=Sum('amount_paid'))['total'] or Decimal('0')
#         pending_payment = all_invoices.filter(status__in=['pending', 'partial']).aggregate(total=Sum('balance_due'))['total'] or Decimal('0')

#         # Recent items
#         recent_orders = all_orders[:5]
#         recent_invoices = all_invoices[:5]

#         # Unread notifications
#         unread_count = Notification.objects.filter(user=request.user, is_read=False).count()

#         dashboard_data = {
#             'total_orders': all_orders.count(),
#             'pending_orders': all_orders.filter(status__in=['open', 'accepted', 'in_transit']).count(),
#             'completed_orders': completed_orders.count(),
#             'total_supplied_kg': total_supplied,
#             'total_earned': total_earned,
#             'pending_payment': pending_payment,
#             'recent_orders': SourceOrderListSerializer(recent_orders, many=True).data,
#             'recent_invoices': SupplierInvoiceSerializer(recent_invoices, many=True).data,
#             'unread_notifications': unread_count,
#         }

#         serializer = SupplierDashboardSerializer(dashboard_data)
#         return Response(serializer.data)









