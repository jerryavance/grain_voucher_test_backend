# sourcing/permissions.py
from rest_framework.permissions import BasePermission

STAFF_ROLES = ['super_admin', 'hub_admin', 'bdm', 'finance']


class IsStaff(BasePermission):
    """Any internal staff role: super_admin, hub_admin, bdm, finance."""

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role in STAFF_ROLES
        )


class IsSupplier(BasePermission):
    """Authenticated user who has a supplier profile (farmer role)."""

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'supplier_profile')
        )


class IsStaffOrSupplier(BasePermission):
    """Either a staff member OR a supplier — used on shared read endpoints."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return (
            request.user.role in STAFF_ROLES or
            hasattr(request.user, 'supplier_profile')
        )


class IsHubAdminOrBDM(BasePermission):
    """Hub admins, BDMs, and finance — legacy alias kept for compatibility."""

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role in ['hub_admin', 'bdm', 'finance']
        )


class IsSupplierOwner(BasePermission):
    """
    Object-level permission: the requesting user must own the object.
    Works for SupplierProfile (has .user) and PaymentPreference (has .supplier).
    Staff always pass.
    """

    def has_object_permission(self, request, view, obj):
        if request.user.role in STAFF_ROLES:
            return True

        # PaymentPreference or any object linked via .supplier FK
        if hasattr(obj, 'supplier'):
            return obj.supplier.user == request.user

        # SupplierProfile itself
        if hasattr(obj, 'user'):
            return obj.user == request.user

        return False


class IsSupplierOrderOwner(BasePermission):
    """
    Object-level: supplier can only access their own SourceOrder.
    Staff can access any order.
    """

    def has_object_permission(self, request, view, obj):
        if request.user.role in STAFF_ROLES:
            return True
        if hasattr(request.user, 'supplier_profile'):
            return obj.supplier == request.user.supplier_profile
        return False


class CanManageSourceOrder(BasePermission):
    """
    View-level:  only staff may POST (create) a new source order.
    Object-level:
      - staff can PUT / PATCH / DELETE any order
      - suppliers can only read their own (enforced via get_queryset +
        IsSupplierOrderOwner at object level)
    """

    def has_permission(self, request, view):
        if request.method == 'POST':
            return (
                request.user and
                request.user.is_authenticated and
                request.user.role in STAFF_ROLES
            )
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.method in ['PUT', 'PATCH', 'DELETE']:
            return request.user.role in STAFF_ROLES

        if request.user.role in STAFF_ROLES:
            return True
        if hasattr(request.user, 'supplier_profile'):
            return obj.supplier == request.user.supplier_profile
        return False




# # sourcing/permissions.py
# from rest_framework.permissions import BasePermission


# class IsSupplier(BasePermission):
#     """Permission for users with farmer role who have a supplier profile"""
    
#     def has_permission(self, request, view):
#         return (
#             request.user and 
#             request.user.is_authenticated and 
#             hasattr(request.user, 'supplier_profile')
#         )


# class IsHubAdminOrBDM(BasePermission):
#     """Permission for hub admins and BDM users"""
    
#     def has_permission(self, request, view):
#         return (
#             request.user and 
#             request.user.is_authenticated and 
#             request.user.role in ['hub_admin', 'bdm', 'finance', 'super_admin']
#         )


# class IsSupplierOwner(BasePermission):
#     """Permission to check if user owns the supplier profile"""
    
#     def has_object_permission(self, request, view, obj):
#         # For PaymentPreference objects
#         if hasattr(obj, 'supplier'):
#             return obj.supplier.user == request.user
        
#         # For SupplierProfile objects
#         if hasattr(obj, 'user'):
#             return obj.user == request.user
        
#         return False


# class CanManageSourceOrder(BasePermission):
#     """Permission for managing source orders"""
    
#     def has_permission(self, request, view):
#         # Hub admins and BDMs can create orders
#         if request.method == 'POST':
#             return request.user.role in ['hub_admin', 'bdm', 'finance']
#         return True
    
#     def has_object_permission(self, request, view, obj):
#         # Hub admins and BDMs can update/delete
#         if request.method in ['PUT', 'PATCH', 'DELETE']:
#             return request.user.role in ['hub_admin', 'bdm', 'finance']
        
#         # Suppliers can view their own orders
#         if hasattr(request.user, 'supplier_profile'):
#             return obj.supplier == request.user.supplier_profile
        
#         # Staff can view all
#         return request.user.role in ['hub_admin', 'bdm', 'finance']