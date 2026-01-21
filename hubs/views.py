# hubs/views.py
from rest_framework import status
from .models import Hub
from .serializers import HubSerializer, HubCreateUpdateSerializer
from utils.permissions import IsSuperAdmin, IsSuperAdminOrReadOnly
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import get_user_model
from django.db.models import Q
from hubs.models import Hub
from .models import HubMembership
from .serializers import (
    HubMembershipRequestSerializer,
    HubMembershipSerializer,
    HubMembershipApprovalSerializer,
    UserHubListSerializer
)

User = get_user_model()

class HubViewSet(ModelViewSet):
    queryset = Hub.objects.all()
    # permission_classes = [IsAuthenticated, IsSuperAdmin]
    permission_classes =[IsSuperAdminOrReadOnly]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return HubCreateUpdateSerializer
        return HubSerializer


    @action(detail=False, methods=['post'], permission_classes=[IsSuperAdmin])
    def assign_admin(self, request):
        user_id = request.data.get('user_id')
        hub_id = request.data.get('hub_id')

        if not hub_id:
            return Response({"error": "hub_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = get_user_model().objects.get(id=user_id)
            if user.role != 'hub_admin':
                return Response({"error": "User must have role hub_admin"}, status=status.HTTP_400_BAD_REQUEST)

            # Check if membership already exists
            membership, created = HubMembership.objects.get_or_create(
                user=user,
                hub_id=hub_id,
                role="hub_admin",
                defaults={"status": "active"}
            )

            if not created:
                if membership.status == "inactive":
                    membership.status = "active"
                    membership.save()
                    return Response({"message": "Hub admin reactivated successfully"}, status=status.HTTP_200_OK)
                else:
                    return Response({"error": "Hub admin already assigned to this hub"}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"message": "Hub admin assigned successfully"}, status=status.HTTP_201_CREATED)

        except get_user_model().DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)



    @action(detail=False, methods=['post'], permission_classes=[IsSuperAdmin])
    def unassign_admin(self, request):
        user_id = request.data.get('user_id')
        hub_id = request.data.get('hub_id')

        if not hub_id:
            return Response({"error": "hub_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = get_user_model().objects.get(id=user_id)
            if user.role != 'hub_admin':
                return Response({"error": "User must have role hub_admin"}, status=status.HTTP_400_BAD_REQUEST)

            membership = HubMembership.objects.filter(
                user=user,
                hub_id=hub_id,
                role="hub_admin",
                status="active"
            ).first()

            if not membership:
                return Response({"error": "This hub admin is not actively assigned to the hub"}, status=status.HTTP_400_BAD_REQUEST)

            # Soft unassign → mark inactive
            membership.status = "inactive"
            membership.save()

            return Response({"message": "Hub admin unassigned successfully"}, status=status.HTTP_200_OK)

        except get_user_model().DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

class HubMembershipViewSet(ModelViewSet):
    serializer_class = HubMembershipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter memberships based on user role safely"""
        # Short-circuit for schema generation (Swagger/OpenAPI)
        if getattr(self, 'swagger_fake_view', False):
            return HubMembership.objects.none()

        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return HubMembership.objects.none()

        # Super admin can see all memberships
        if getattr(user, 'role', None) == 'super_admin':
            return HubMembership.objects.select_related('user', 'hub', 'approved_by').all()

        # Hub admins can see memberships for their hubs
        if getattr(user, 'role', None) == 'hub_admin':
            admin_hubs = HubMembership.objects.filter(
                user=user,
                role='hub_admin', 
                status='active'
            ).values_list('hub', flat=True)
            
            if admin_hubs:
                return HubMembership.objects.filter(
                    hub__in=admin_hubs
                ).select_related('user', 'hub', 'approved_by').order_by('-requested_at')
        
        # Regular users can only see their own memberships
        return HubMembership.objects.filter(user=user).select_related('hub', 'approved_by').order_by('-requested_at')

    
    def get_serializer_class(self):
        if self.action == 'request_membership':
            return HubMembershipRequestSerializer
        elif self.action in ['approve', 'reject']:
            return HubMembershipApprovalSerializer
        return HubMembershipSerializer
    
    @action(detail=False, methods=['post'])
    def request_membership(self, request):
        """User requests to join a hub"""
        serializer = HubMembershipRequestSerializer(
            data=request.data, 
            context={'request': request}
        )
        
        if serializer.is_valid():
            membership = serializer.save()
            return Response({
                'message': 'Membership request submitted successfully',
                'membership': HubMembershipSerializer(membership).data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Hub admin approves a membership request"""
        membership = self.get_object()
        user = request.user
        
        # Check if user can approve this membership
        if not self._can_manage_membership(user, membership.hub):
            return Response(
                {'error': 'You do not have permission to manage this hub'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if membership.status != 'pending':
            return Response(
                {'error': 'Only pending memberships can be approved'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = HubMembershipApprovalSerializer(
            membership, 
            data={'status': 'active', **request.data},
            context={'request': request},
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Membership approved successfully',
                'membership': HubMembershipSerializer(membership).data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Hub admin rejects a membership request"""
        membership = self.get_object()
        user = request.user
        
        if not self._can_manage_membership(user, membership.hub):
            return Response(
                {'error': 'You do not have permission to manage this hub'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if membership.status not in ['pending', 'active']:
            return Response(
                {'error': 'Cannot reject this membership'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = HubMembershipApprovalSerializer(
            membership,
            data={'status': 'rejected', **request.data},
            context={'request': request},
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Membership rejected',
                'membership': HubMembershipSerializer(membership).data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        """User leaves a hub"""
        membership = self.get_object()
        
        if membership.user != request.user:
            return Response(
                {'error': 'You can only leave your own memberships'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if membership.status != 'active':
            return Response(
                {'error': 'You are not an active member of this hub'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        membership.status = 'inactive'
        membership.save()
        
        return Response({'message': 'You have left the hub successfully'})
    
    # def _can_manage_membership(self, user, hub):
    #     """Check if user can manage memberships for this hub"""
    #     if user.role == 'super_admin':
    #         return True
        
    #     return user.hub_memberships.filter(
    #         hub=hub,
    #         role='hub_admin',
    #         status='active'
    #     ).exists()
    def _can_manage_membership(self, user, hub):
        # Super admins can always manage
        if user.role == "super_admin":
            return True

        # Check if user is an active hub_admin of this hub
        return HubMembership.objects.filter(
            user=user,
            hub=hub,
            role="hub_admin",
            status="active"
        ).exists()


@api_view(['GET'])
@permission_classes([AllowAny])
def search_hubs(request):
    """Public endpoint to search hubs by location/name"""
    query = request.GET.get('q', '').strip()
    location = request.GET.get('location', '').strip()
    
    hubs = Hub.objects.filter(is_active=True)
    
    if query:
        hubs = hubs.filter(
            Q(name__icontains=query) | Q(location__icontains=query)
        )
    
    if location:
        hubs = hubs.filter(location__icontains=location)
    
    hubs = hubs.order_by('name')[:50]  # Limit to 50 results
    
    # Public hub info
    hub_data = []
    for hub in hubs:
        active_members = hub.memberships.filter(status='active').count()
        hub_data.append({
            'id': str(hub.id),
            'name': hub.name,
            'location': hub.location,
            'member_count': active_members,
            'member_count_display': _get_member_count_display(active_members),
        })
    
    return Response({
        'results': hub_data,
        'count': len(hub_data)
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_hubs(request):
    """Get user's hub memberships"""
    user = request.user
    memberships = user.hub_memberships.select_related('hub').order_by('-requested_at')
    
    data = []
    for membership in memberships:
        data.append({
            'id': str(membership.id),
            'hub': {
                'id': str(membership.hub.id),
                'name': membership.hub.name,
                'location': membership.hub.location,
            },
            'role': membership.role,
            'status': membership.status,
            'requested_at': membership.requested_at,
            'approved_at': membership.approved_at,
        })
    
    return Response({
        'results': data,
        'count': len(data)
    })

def _get_member_count_display(count):
    """Convert member count to display range for privacy"""
    if count == 0:
        return "New hub"
    elif count <= 5:
        return "1-5 members"
    elif count <= 20:
        return "6-20 members"
    elif count <= 50:
        return "21-50 members"
    elif count <= 100:
        return "51-100 members"
    else:
        return "100+ members"
