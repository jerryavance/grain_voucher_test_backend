# vouchers/views.py
from django.db.models import Q
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from hubs.views import User
from vouchers.models import (
    GrainType, QualityGrade, PriceFeed, Deposit, Voucher, 
    Redemption, PurchaseOffer, Inventory, LedgerEntry
)
from vouchers.serializers import (
    GrainTypeSerializer, QualityGradeSerializer, PriceFeedSerializer,
    DepositSerializer, VoucherSerializer, RedemptionSerializer,
    PurchaseOfferSerializer, InventorySerializer, LedgerEntrySerializer
)
from utils.permissions import (
    IsSuperAdmin, IsHubAdmin, IsAgent, IsInvestor, IsFarmer, IsOwnerOrAdmin,
    IsHubAdminForObject, IsSuperAdminOrReadOnly
)
from vouchers.permissions import (
    IsHubAdminForDeposit, IsAgentForDeposit, IsOwnerForVoucher, IsInvestorForOffer
)
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .filters import DepositFilterSet, VoucherFilterSet
from hubs.models import Hub, HubMembership
from hubs.serializers import HubSerializer

# ----------------------------
# READ-ONLY FOR ALL, SUPERADMIN CAN EDIT
# ----------------------------

class GrainTypeViewSet(ModelViewSet):
    queryset = GrainType.objects.all()
    serializer_class = GrainTypeSerializer
    permission_classes = [IsSuperAdminOrReadOnly]  # ✅ read-only for all, editable by super admin

class QualityGradeViewSet(ModelViewSet):
    queryset = QualityGrade.objects.all()
    serializer_class = QualityGradeSerializer
    permission_classes = [IsSuperAdminOrReadOnly]

class HubViewSet(ModelViewSet):
    queryset = Hub.objects.all()
    serializer_class = HubSerializer
    permission_classes = [IsSuperAdminOrReadOnly]

# ----------------------------
# Other ViewSets remain mostly unchanged
# ----------------------------

class PriceFeedViewSet(ModelViewSet):
    queryset = PriceFeed.objects.all()
    serializer_class = PriceFeedSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['hub', 'grain_type', 'effective_date']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()

        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset()
        elif user.role in ['hub_admin', 'agent']:
            hub_ids = user.hub_memberships.filter(
                role__in=['hub_admin', 'agent'],
                status='active'
            ).values_list('hub_id', flat=True)
            return super().get_queryset().filter(hub__in=hub_ids)
        else:
            return super().get_queryset().filter(hub__isnull=True)


    def perform_create(self, serializer):
        user = self.request.user
        if user.role in ['hub_admin', 'super_admin']:
            serializer.save(hub=user.hub if user.role == 'hub_admin' else serializer.validated_data.get('hub'))

class DepositViewSet(ModelViewSet):
    queryset = Deposit.objects.all()
    serializer_class = DepositSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = DepositFilterSet

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update']:
            # Custom permission check in perform_create/update
            return [IsAuthenticated()]
        elif self.action == 'validate_deposit':
            return [IsAuthenticated()]  # Will check hub admin permission in method
        return [IsAuthenticated()]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
            
        user = self.request.user
        
        if user.role == 'super_admin':
            return super().get_queryset()
        
        # Get hubs where user has relevant memberships
        if user.role == 'hub_admin':
            admin_hubs = user.hub_memberships.filter(
                role='hub_admin',
                status='active'
            ).values_list('hub', flat=True)
            return super().get_queryset().filter(hub__in=admin_hubs)
            
        elif user.role == 'agent':
            agent_hubs = user.hub_memberships.filter(
                role='agent',
                status='active'
            ).values_list('hub', flat=True)
            return super().get_queryset().filter(hub__in=agent_hubs, agent=user)
            
        elif user.role == 'farmer':
            farmer_hubs = user.hub_memberships.filter(
                status='active'
            ).values_list('hub', flat=True)
            return super().get_queryset().filter(
                hub__in=farmer_hubs,
                farmer=user
            )
        
        return super().get_queryset().none()

    @action(detail=True, methods=['post'])
    def validate_deposit(self, request, pk=None):
        deposit = self.get_object()
        user = request.user
        
        # Check if user can validate deposits for this hub
        can_validate = False
        
        if user.role == 'super_admin':
            can_validate = True
        elif user.role == 'hub_admin':
            can_validate = user.hub_memberships.filter(
                hub=deposit.hub,
                role='hub_admin',
                status='active'
            ).exists()
        
        if not can_validate:
            return Response(
                {"error": "You do not have permission to validate deposits for this hub"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if deposit.validated:
            return Response(
                {"error": "Already validated"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        deposit.validated = True
        deposit.save()
        return Response(
            {"message": "Deposit validated"}, 
            status=status.HTTP_200_OK
        )



    @action(detail=False, methods=['get'])
    def available_farmers(self, request):
        """Get farmers available for deposits in user's hubs"""
        user = request.user
        hub_id = request.query_params.get('hub_id')

        if not hub_id:
            return Response(
                {"error": "hub_id parameter is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            hub = Hub.objects.get(id=hub_id)
        except Hub.DoesNotExist:
            return Response(
                {"error": "Hub not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        if user.role not in ['super_admin']:
            user_membership = user.hub_memberships.filter(
                hub=hub,
                role__in=['hub_admin', 'agent'],
                status='active'
            ).first()

            if not user_membership:
                return Response(
                    {"error": "You do not have permission to access this hub's farmers"}, 
                    status=status.HTTP_403_FORBIDDEN
                )

        farmer_ids = HubMembership.objects.filter(
            hub=hub,
            role='farmer',
            status='active'
        ).values_list('user', flat=True)

        farmers = User.objects.filter(id__in=farmer_ids)

        search = request.query_params.get('search', '').strip()
        if search:
            farmers = farmers.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(phone_number__icontains=search)
            )

        farmers = farmers.order_by('first_name', 'last_name')

        page = self.paginate_queryset(farmers)
        farmer_data = [{
            'id': str(f.id),
            'name': f"{f.first_name} {f.last_name}".strip(),
            'phone_number': f.phone_number,
        } for f in (page if page is not None else farmers)]

        if page is not None:
            return self.get_paginated_response(farmer_data)

        return Response({"results": farmer_data})
        
class VoucherViewSet(ModelViewSet):
    queryset = Voucher.objects.all()
    serializer_class = VoucherSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = VoucherFilterSet

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()

        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset()
        elif user.role == 'hub_admin':
            hub_ids = user.hub_memberships.filter(
                role='hub_admin',
                status='active'
            ).values_list('hub_id', flat=True)
            return super().get_queryset().filter(deposit__hub__in=hub_ids)
        elif user.role in ['farmer', 'investor']:
            return super().get_queryset().filter(holder=user)
        elif user.role == 'agent':
            hub_ids = user.hub_memberships.filter(
                role='agent',
                status='active'
            ).values_list('hub_id', flat=True)
            return super().get_queryset().filter(deposit__hub__in=hub_ids, deposit__agent=user)
        return super().get_queryset().none()

    @action(detail=True, methods=['post'])
    def verify_voucher(self, request, pk=None):
        """Verify a voucher (hub admin only)"""
        voucher = self.get_object()
        user = request.user
        
        # Check if user can verify vouchers for this hub
        can_verify = False
        
        if user.role == 'super_admin':
            can_verify = True
        elif user.role == 'hub_admin':
            can_verify = user.hub_memberships.filter(
                hub=voucher.deposit.hub,
                role='hub_admin',
                status='active'
            ).exists()
        
        if not can_verify:
            return Response(
                {"error": "You do not have permission to verify vouchers for this hub"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if voucher.verification_status != 'pending':
            return Response(
                {"error": "Voucher is not pending verification"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        voucher.verification_status = 'verified'
        voucher.verified_by = user
        voucher.save()
        
        return Response(
            {"message": "Voucher verified successfully"}, 
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def reject_voucher(self, request, pk=None):
        """Reject a voucher (hub admin only)"""
        voucher = self.get_object()
        user = request.user
        
        # Check permissions (same as verify)
        can_reject = False
        
        if user.role == 'super_admin':
            can_reject = True
        elif user.role == 'hub_admin':
            can_reject = user.hub_memberships.filter(
                hub=voucher.deposit.hub,
                role='hub_admin',
                status='active'
            ).exists()
        
        if not can_reject:
            return Response(
                {"error": "You do not have permission to reject vouchers for this hub"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if voucher.verification_status != 'pending':
            return Response(
                {"error": "Voucher is not pending verification"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        rejection_reason = request.data.get('reason', '')
        
        voucher.verification_status = 'rejected'
        voucher.verified_by = user
        voucher.status = 'rejected'
        voucher.save()
        
        # Create ledger entry for rejection
        LedgerEntry.objects.create(
            event_type='voucher_rejected',
            related_object_id=voucher.id,
            user=user,
            hub=voucher.deposit.hub,
            description=f"Voucher rejected: {rejection_reason}",
            amount=Decimal('0.00')
        )
        
        return Response(
            {"message": "Voucher rejected"}, 
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'])
    def pending_verification(self, request):
        """Get vouchers pending verification (hub admin only)"""
        user = request.user
        
        if user.role not in ['super_admin', 'hub_admin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Filter vouchers pending verification in user's hubs
        queryset = self.get_queryset().filter(verification_status='pending')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({"results": serializer.data})

    # @action(detail=False, methods=['get'])
    # def my_vouchers(self, request):
    #     qs = self.get_queryset().filter(holder=request.user)
    #     page = self.paginate_queryset(qs)
    #     if page is not None:
    #         serializer = self.get_serializer(page, many=True)
    #         return self.get_paginated_response(serializer.data)
    #     serializer = self.get_serializer(qs, many=True)
    #     return Response({"results": serializer.data})

    @action(detail=False, methods=['get'])
    def my_vouchers(self, request):
        user = request.user

        # ✅ Super admin sees all vouchers
        if user.role == 'super_admin':
            qs = self.get_queryset()
        else:
            qs = self.get_queryset().filter(holder=user)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return Response({"results": serializer.data})


    @action(detail=False, methods=['get'], permission_classes=[IsInvestor])
    def available_for_purchase(self, request):
        # Only show verified vouchers for purchase
        qs = Voucher.objects.filter(
            status='issued',
            verification_status='verified'
        ).exclude(holder__role='investor')
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response({"results": serializer.data})

class RedemptionViewSet(ModelViewSet):
    queryset = Redemption.objects.all()
    serializer_class = RedemptionSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action == 'create':
            return [IsOwnerForVoucher()]  # Only holder can request redemption
        elif self.action in ['update', 'partial_update']:
            return [IsHubAdmin() | IsSuperAdmin()]  # Approve/reject
        return [IsAuthenticated()]


    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()

        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset()
        elif user.role == 'hub_admin':
            hub_ids = user.hub_memberships.filter(
                role='hub_admin',
                status='active'
            ).values_list('hub_id', flat=True)
            return super().get_queryset().filter(voucher__deposit__hub__in=hub_ids)
        elif user.role in ['farmer', 'investor']:
            return super().get_queryset().filter(requester=user)
        return super().get_queryset().none()


    @action(detail=True, methods=['post'], permission_classes=[IsHubAdmin | IsSuperAdmin])
    def approve(self, request, pk=None):
        redemption = self.get_object()
        if redemption.status != 'pending':
            return Response({"error": "Not pending"}, status=status.HTTP_400_BAD_REQUEST)
        redemption.status = 'approved'
        redemption.save()
        # Trigger payment process (integrate with payment gateway if needed)
        return Response({"message": "Approved"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsHubAdmin | IsSuperAdmin])
    def pay(self, request, pk=None):
        redemption = self.get_object()
        if redemption.status != 'approved':
            return Response({"error": "Not approved"}, status=status.HTTP_400_BAD_REQUEST)
        redemption.status = 'paid'
        redemption.save()
        # Ledger entry already in signal
        return Response({"message": "Paid"}, status=status.HTTP_200_OK)

class PurchaseOfferViewSet(ModelViewSet):
    queryset = PurchaseOffer.objects.all()
    serializer_class = PurchaseOfferSerializer
    permission_classes = [IsAuthenticated, IsInvestor]
    # pagination_class = None

    def get_queryset(self):
        # Handle schema generation and unauthenticated requests
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
            
        user = self.request.user
        qs = super().get_queryset()
        if user.role == 'super_admin':
            return qs
        elif user.role == 'hub_admin':
            return qs.filter(voucher__deposit__hub=user.hub)
        elif user.role == 'investor':
            return qs.filter(investor=user)
        return qs.none()

    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin | IsHubAdmin])
    def accept(self, request, pk=None):
        offer = self.get_object()
        if offer.status != 'pending':
            return Response({"error": "Not pending"}, status=status.HTTP_400_BAD_REQUEST)
        offer.status = 'accepted'
        offer.save()
        # Trigger transfer via signal
        return Response({"message": "Accepted"}, status=status.HTTP_200_OK)

class InventoryViewSet(ModelViewSet):
    queryset = Inventory.objects.all()
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Handle schema generation and unauthenticated requests
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()

        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset()
        elif user.role in ['hub_admin', 'agent']:
            hub_ids = user.hub_memberships.filter(
                role__in=['hub_admin', 'agent'],
                status='active'
            ).values_list('hub_id', flat=True)
            return super().get_queryset().filter(hub__in=hub_ids)
        return super().get_queryset().none()


class LedgerEntryViewSet(ModelViewSet):
    queryset = LedgerEntry.objects.all()
    serializer_class = LedgerEntrySerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin | IsHubAdmin]  # Restricted
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['event_type', 'user', 'hub', 'timestamp']

    def get_queryset(self):
        # Handle schema generation and unauthenticated requests
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
            
        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset()
        elif user.role == 'hub_admin':
            return super().get_queryset().filter(hub=user.hub)
        return super().get_queryset().none()