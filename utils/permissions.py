from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsSuperAdminOrReadOnly(BasePermission):
    """
    Allow read-only access to all users.
    Only super admins can create, update, delete.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:  # GET, HEAD, OPTIONS
            return request.user.is_authenticated  # All authenticated users can view
        # Only super admin can POST, PUT, PATCH, DELETE
        return request.user.is_authenticated and request.user.role == "super_admin"


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'super_admin'


class IsHubAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'hub_admin'


class IsHubAdminForObject(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.hub == obj.hub if hasattr(obj, 'hub') else False


class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.role in ['super_admin', 'hub_admin']:
            return True
        return obj == request.user


class IsAgent(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'agent'


class IsInvestor(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'investor'


class IsFarmer(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'farmer'


class IsOwnerOrHubAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'super_admin':
            return True
        if request.user.role == 'hub_admin' and obj.hub == request.user.hub:
            return True
        return obj.user == request.user if hasattr(obj, 'user') else False


class IsBDM(BasePermission):
    def has_permission(self, request, view):
        return request.user.role == 'bdm'


class IsClient(BasePermission):
    def has_permission(self, request, view):
        return request.user.role == 'client'

class IsFinance(BasePermission):
    def has_permission(self, request, view):
        return request.user.role == 'finance'