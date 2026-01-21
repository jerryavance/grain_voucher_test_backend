# reports/permissions.py
from rest_framework import permissions


class CanGenerateReports(permissions.BasePermission):
    """
    Permission to generate reports.
    Allowed roles: super_admin, finance, hub_admin
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in ['super_admin', 'finance', 'hub_admin']
        )


class CanViewAllReports(permissions.BasePermission):
    """
    Permission to view all reports across all hubs.
    Allowed roles: super_admin, finance
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in ['super_admin', 'finance']
        )


class CanScheduleReports(permissions.BasePermission):
    """
    Permission to create scheduled reports.
    Allowed roles: super_admin, finance
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in ['super_admin', 'finance']
        )