# sourcing/permissions.py
from rest_framework.permissions import BasePermission


class IsSupplier(BasePermission):
    """Permission for users with farmer role who have a supplier profile"""
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            hasattr(request.user, 'supplier_profile')
        )


class IsHubAdminOrBDM(BasePermission):
    """Permission for hub admins and BDM users"""
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in ['hub_admin', 'bdm', 'finance']
        )


class IsSupplierOwner(BasePermission):
    """Permission to check if user owns the supplier profile"""
    
    def has_object_permission(self, request, view, obj):
        # For PaymentPreference objects
        if hasattr(obj, 'supplier'):
            return obj.supplier.user == request.user
        
        # For SupplierProfile objects
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        return False


class CanManageSourceOrder(BasePermission):
    """Permission for managing source orders"""
    
    def has_permission(self, request, view):
        # Hub admins and BDMs can create orders
        if request.method == 'POST':
            return request.user.role in ['hub_admin', 'bdm', 'finance']
        return True
    
    def has_object_permission(self, request, view, obj):
        # Hub admins and BDMs can update/delete
        if request.method in ['PUT', 'PATCH', 'DELETE']:
            return request.user.role in ['hub_admin', 'bdm', 'finance']
        
        # Suppliers can view their own orders
        if hasattr(request.user, 'supplier_profile'):
            return obj.supplier == request.user.supplier_profile
        
        # Staff can view all
        return request.user.role in ['hub_admin', 'bdm', 'finance']