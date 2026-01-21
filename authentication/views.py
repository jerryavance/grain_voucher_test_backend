# authentication/views.py
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from authentication.serializers import (
    OTPRequestSerializer, OTPVerificationSerializer, UserRegistrationSerializer,
    UserSerializer, PhoneLoginSerializer
)
from authentication.models import OTPVerification, PhoneVerificationLog
from authentication.filters import UserFilterSet  # Add this import
from rest_framework.permissions import IsAuthenticated, AllowAny
from utils.permissions import IsHubAdmin
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.core.cache import cache
from hubs.models import HubMembership
from datetime import timedelta
import logging
from authentication.filters import UserFilterSet
from hubs.models import Hub

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
def request_otp(request):
    serializer = OTPRequestSerializer(data=request.data, context={'request': request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    phone_number = serializer.validated_data['phone_number']
    purpose = serializer.validated_data['purpose']
    
    cache_key = f"otp_request_{phone_number}_{purpose}"
    request_count = cache.get(cache_key, 0)
    if request_count >= 5:
        return Response({"error": "Too many requests. Try again later."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    
    try:
        digits_only = ''.join(filter(str.isdigit, phone_number))
        if len(digits_only) >= 4:
            test_otp_code = digits_only[-4:]
        else:
            test_otp_code = digits_only.zfill(4)
        
        otp_record = OTPVerification.objects.create(
            phone_number=phone_number,
            otp_code=test_otp_code,
            purpose=purpose
        )
        
        logger.info(f"[TEST MODE] OTP for {phone_number}: {otp_record.otp_code} (last 4 digits of phone)")
        
        PhoneVerificationLog.objects.create(
            phone_number=phone_number,
            purpose=purpose,
            status='sent'
        )
        
        cache.set(cache_key, request_count + 1, timeout=3600)
        
        return Response({"message": "OTP sent successfully"}, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error requesting OTP for {phone_number}: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    serializer = OTPVerificationSerializer(data=request.data, context={'request': request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    otp_record = serializer.validated_data['otp_record']
    phone_number = serializer.validated_data['phone_number']
    
    try:
        PhoneVerificationLog.objects.create(
            phone_number=phone_number,
            purpose=otp_record.purpose,
            status='verified'
        )
        return Response({"message": "OTP verified successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error verifying OTP for {phone_number}: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    serializer = UserRegistrationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.error(f"Error during registration: {e}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def login_with_phone(request):
    serializer = PhoneLoginSerializer(data=request.data, context={'request': request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    user = serializer.validated_data['user']
    refresh = RefreshToken.for_user(user)
    
    return Response({
        'refresh': str(refresh),
        'access': str(refresh.access_token),
        'user': UserSerializer(user).data
    }, status=status.HTTP_200_OK)


class UserViewSet(ModelViewSet):
    queryset = get_user_model().objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = UserFilterSet  # Add this line to enable filtering

    def get_queryset(self):
        # Handle schema generation and unauthenticated requests
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return super().get_queryset().none()
        
        user = self.request.user
        if user.role == 'super_admin':
            return super().get_queryset().order_by('-id')
        elif user.role in ['hub_admin', 'agent']:
            admin_hubs = user.hub_memberships.filter(
                status='active'
            ).values_list('hub', flat=True)
            return super().get_queryset().filter(
                hub_memberships__hub__in=admin_hubs
            ).distinct().order_by('-id')
        else:
            return super().get_queryset().filter(id=user.id).order_by('-id')

    @action(detail=False, methods=['post'], permission_classes=[IsHubAdmin])
    def assign_agent(self, request):
        user_id = request.data.get('user_id')
        hub_id = request.data.get('hub_id')

        if not hub_id:
            return Response({"error": "hub_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = get_user_model().objects.get(id=user_id)
            if user.role != 'agent':
                return Response({"error": "User must be an agent"}, status=status.HTTP_400_BAD_REQUEST)

            # Ensure current user is admin of this hub
            if not HubMembership.objects.filter(
                user=request.user,
                hub_id=hub_id,
                role="hub_admin",
                status="active"
            ).exists():
                return Response(
                    {"error": "You cannot assign agents to this hub"},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Check if membership already exists
            membership, created = HubMembership.objects.get_or_create(
                user=user,
                hub_id=hub_id,
                role="agent",
                defaults={"status": "active"}
            )

            if not created:
                if membership.status == "inactive":
                    membership.status = "active"
                    membership.save()
                    return Response({"message": "Agent reactivated successfully"}, status=status.HTTP_200_OK)
                else:
                    return Response({"error": "Agent is already assigned to this hub"}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"message": "Agent assigned successfully"}, status=status.HTTP_201_CREATED)

        except get_user_model().DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


    @action(detail=False, methods=['post'], permission_classes=[IsHubAdmin])
    def unassign_agent(self, request):
        user_id = request.data.get('user_id')
        hub_id = request.data.get('hub_id')

        if not hub_id:
            return Response({"error": "hub_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = get_user_model().objects.get(id=user_id)
            if user.role != 'agent':
                return Response({"error": "User must be an agent"}, status=status.HTTP_400_BAD_REQUEST)

            # Ensure current user is admin of this hub
            if not HubMembership.objects.filter(
                user=request.user,
                hub_id=hub_id,
                role="hub_admin",
                status="active"
            ).exists():
                return Response(
                    {"error": "You cannot unassign agents from this hub"},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Find the membership
            membership = HubMembership.objects.filter(
                user=user,
                hub_id=hub_id,
                role="agent",
                status="active"
            ).first()

            if not membership:
                return Response(
                    {"error": "This agent is not actively assigned to the hub"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Soft unassign → mark inactive
            membership.status = "inactive"
            membership.save()

            return Response(
                {"message": "Agent unassigned successfully"},
                status=status.HTTP_200_OK
            )

        except get_user_model().DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)