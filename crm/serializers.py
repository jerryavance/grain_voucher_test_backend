# crm/serializers.py
from rest_framework import serializers
from .models import Lead, Account, Contact, Opportunity, Contract
from authentication.serializers import UserSerializer
from hubs.serializers import HubSerializer
from authentication.models import GrainUser
from hubs.models import Hub

class LeadSerializer(serializers.ModelSerializer):
    assigned_to = UserSerializer(read_only=True)
    assigned_to_id = serializers.PrimaryKeyRelatedField(queryset=GrainUser.objects.filter(role='bdm'), source='assigned_to', write_only=True)

    class Meta:
        model = Lead
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        # Ensure assigned_to is BDM
        if 'assigned_to' in data and data['assigned_to'].role != 'bdm':
            raise serializers.ValidationError("Assigned user must be a BDM.")
        return data

class AccountSerializer(serializers.ModelSerializer):
    hub = HubSerializer(read_only=True)
    hub_id = serializers.PrimaryKeyRelatedField(queryset=Hub.objects.all(), source='hub', write_only=True, required=False)

    class Meta:
        model = Account
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

class ContactSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(queryset=GrainUser.objects.filter(role='client'), source='user', write_only=True, required=False)

    class Meta:
        model = Contact
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

class OpportunitySerializer(serializers.ModelSerializer):
    account = AccountSerializer(read_only=True)
    account_id = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all(), source='account', write_only=True)
    assigned_to = UserSerializer(read_only=True)
    assigned_to_id = serializers.PrimaryKeyRelatedField(queryset=GrainUser.objects.filter(role='bdm'), source='assigned_to', write_only=True)

    class Meta:
        model = Opportunity
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

class ContractSerializer(serializers.ModelSerializer):
    opportunity = OpportunitySerializer(read_only=True)
    opportunity_id = serializers.PrimaryKeyRelatedField(queryset=Opportunity.objects.all(), source='opportunity', write_only=True)

    class Meta:
        model = Contract
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']