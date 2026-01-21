# investors/views.py
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.core.exceptions import ValidationError

from utils.permissions import IsSuperAdmin, IsHubAdmin, IsInvestor
from .models import InvestorAccount, InvestorDeposit, InvestorWithdrawal, ProfitSharingAgreement
from .serializers import (
    InvestorAccountSerializer, InvestorDepositSerializer, InvestorWithdrawalSerializer,
    ProfitSharingAgreementSerializer, InvestorDashboardSerializer
)
from vouchers.models import LedgerEntry


class InvestorAccountViewSet(ModelViewSet):
    queryset = InvestorAccount.objects.all()
    serializer_class = InvestorAccountSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin | IsHubAdmin | IsInvestor]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['investor']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset()
        elif user.role == 'hub_admin':
            hub_ids = user.hub_memberships.filter(role='hub_admin', status='active').values_list('hub_id', flat=True)
            return super().get_queryset().filter(investor__hub_memberships__hub__in=hub_ids)
        elif user.role == 'investor':
            return super().get_queryset().filter(investor=user)
        return super().get_queryset().none()

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsInvestor | IsSuperAdmin ])
    def dashboard(self, request):
        """Get investor dashboard with comprehensive statistics"""
        try:
            account = InvestorAccount.objects.get(investor=request.user)
            serializer = InvestorDashboardSerializer(account)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except InvestorAccount.DoesNotExist:
            return Response(
                {"error": "Investor account not found"},
                status=status.HTTP_404_NOT_FOUND
            )

class InvestorDepositViewSet(ModelViewSet):
    queryset = InvestorDeposit.objects.all()
    serializer_class = InvestorDepositSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin | IsHubAdmin | IsInvestor]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['investor_account']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset()
        elif user.role == 'hub_admin':
            hub_ids = user.hub_memberships.filter(role='hub_admin', status='active').values_list('hub_id', flat=True)
            return super().get_queryset().filter(investor_account__investor__hub_memberships__hub__in=hub_ids)
        elif user.role == 'investor':
            return super().get_queryset().filter(investor_account__investor=user)
        return super().get_queryset().none()


class InvestorWithdrawalViewSet(ModelViewSet):
    queryset = InvestorWithdrawal.objects.all()
    serializer_class = InvestorWithdrawalSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin | IsHubAdmin | IsInvestor]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['investor_account', 'status']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset()
        elif user.role == 'hub_admin':
            hub_ids = user.hub_memberships.filter(role='hub_admin', status='active').values_list('hub_id', flat=True)
            return super().get_queryset().filter(investor_account__investor__hub_memberships__hub__in=hub_ids)
        elif user.role == 'investor':
            return super().get_queryset().filter(investor_account__investor=user)
        return super().get_queryset().none()

    def perform_create(self, serializer):
        """Create withdrawal request"""
        with transaction.atomic():
            withdrawal = serializer.save(status='pending')
            LedgerEntry.objects.create(
                event_type='withdrawal_request',
                related_object_id=withdrawal.id,
                user=withdrawal.investor_account.investor,
                hub=None,
                description=f"Withdrawal request of {withdrawal.amount} UGX",
                amount=-withdrawal.amount
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsSuperAdmin | IsHubAdmin])
    def approve(self, request, pk=None):
        """Approve withdrawal request"""
        withdrawal = self.get_object()
        
        if withdrawal.status != 'pending':
            return Response(
                {"error": "Withdrawal is not in pending status"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            try:
                withdrawal.approve(approved_by=request.user)
                LedgerEntry.objects.create(
                    event_type='withdrawal_approved',
                    related_object_id=withdrawal.id,
                    user=withdrawal.investor_account.investor,
                    hub=None,
                    description=f"Withdrawal of {withdrawal.amount} UGX approved",
                    amount=-withdrawal.amount
                )
                return Response(
                    {"message": "Withdrawal approved"},
                    status=status.HTTP_200_OK
                )
            except ValidationError as e:
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsSuperAdmin | IsHubAdmin])
    def reject(self, request, pk=None):
        """Reject withdrawal request"""
        withdrawal = self.get_object()
        
        if withdrawal.status != 'pending':
            return Response(
                {"error": "Withdrawal is not in pending status"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        notes = request.data.get('notes', 'Withdrawal rejected')
        
        with transaction.atomic():
            withdrawal.reject(notes=notes)
            LedgerEntry.objects.create(
                event_type='withdrawal_rejected',
                related_object_id=withdrawal.id,
                user=withdrawal.investor_account.investor,
                hub=None,
                description=f"Withdrawal of {withdrawal.amount} UGX rejected: {notes}",
                amount=0
            )
            return Response(
                {"message": "Withdrawal rejected"},
                status=status.HTTP_200_OK
            )


class ProfitSharingAgreementViewSet(ModelViewSet):
    queryset = ProfitSharingAgreement.objects.all()
    serializer_class = ProfitSharingAgreementSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin | IsHubAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['investor_account']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset()
        elif user.role == 'hub_admin':
            hub_ids = user.hub_memberships.filter(role='hub_admin', status='active').values_list('hub_id', flat=True)
            return super().get_queryset().filter(investor_account__investor__hub_memberships__hub__in=hub_ids)
        return super().get_queryset().none()