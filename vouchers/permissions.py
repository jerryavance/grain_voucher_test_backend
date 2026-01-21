from rest_framework.permissions import BasePermission
from vouchers.models import Deposit, Voucher, Redemption, PurchaseOffer

class IsHubAdminForDeposit(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.role == 'hub_admin' and obj.hub == request.user.hub

class IsAgentForDeposit(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.role == 'agent' and obj.agent == request.user and not obj.validated

class IsOwnerForVoucher(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.holder == request.user

class IsInvestorForOffer(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.investor == request.user