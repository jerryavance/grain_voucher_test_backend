# crm/views.py
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from .models import Lead, Account, Contact, Opportunity, Contract
from .serializers import LeadSerializer, AccountSerializer, ContactSerializer, OpportunitySerializer, ContractSerializer
from utils.permissions import IsSuperAdmin, IsHubAdmin, IsBDM  # Assume IsBDM custom permission
from django_filters.rest_framework import DjangoFilterBackend

class LeadViewSet(ModelViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'assigned_to']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()

        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset()
        elif user.role == 'bdm':
            return super().get_queryset().filter(assigned_to=user)
        return super().get_queryset().none()

    @action(detail=True, methods=['post'], permission_classes=[IsBDM])
    def qualify(self, request, pk=None):
        lead = self.get_object()
        if lead.status != 'new':
            return Response({"error": "Lead not new"}, status=status.HTTP_400_BAD_REQUEST)
        lead.status = 'qualified'
        lead.save()
        return Response({"message": "Lead qualified"})

class AccountViewSet(ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin | IsHubAdmin | IsBDM]

class ContactViewSet(ModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin | IsHubAdmin | IsBDM]

class OpportunityViewSet(ModelViewSet):
    queryset = Opportunity.objects.all()
    serializer_class = OpportunitySerializer
    permission_classes = [IsAuthenticated, IsBDM]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
            
        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset()
        return super().get_queryset().filter(assigned_to=user)

class ContractViewSet(ModelViewSet):
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated, IsBDM | IsSuperAdmin]

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        contract = self.get_object()
        if contract.status != 'signed':
            return Response({"error": "Contract not signed"}, status=status.HTTP_400_BAD_REQUEST)
        contract.status = 'executed'
        contract.save()
        # Signal will trigger Trade creation
        return Response({"message": "Contract executed"})