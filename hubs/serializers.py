from django.utils import timezone
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Hub, HubMembership

User = get_user_model()

# Nested admin info
class HubAdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'phone_number']
        read_only_fields = fields

# Read serializer
class HubSerializer(serializers.ModelSerializer):
    hub_admin = serializers.SerializerMethodField()
    class Meta:
        model = Hub
        fields = ['id', 'name', 'slug', 'location', 'is_active', 'hub_admin','created_at', 'updated_at']
        read_only_fields = fields

    def get_hub_admin(self, obj):
        membership = HubMembership.objects.filter(
            hub=obj,
            role="hub_admin",
            status="active"
        ).select_related("user").first()

        return HubAdminUserSerializer(membership.user).data if membership else None


    def get_hub_admin_id(self, obj):
        membership = HubMembership.objects.filter(
            hub=obj,
            role="hub_admin",
            status="active"
        ).first()

        return str(membership.user.id) if membership else None


# Create/Update serializer
class HubCreateUpdateSerializer(serializers.ModelSerializer):
    hub_admin = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Hub
        fields = ['name', 'location', 'is_active', 'hub_admin']

    def validate_hub_admin(self, value):
        if not value:
            return value
        try:
            user = User.objects.get(id=value)
            # Check if user already has an active hub_admin membership
            existing = HubMembership.objects.filter(
                user=user, 
                role="hub_admin", 
                status="active"
            ).exists()
            if existing:
                raise serializers.ValidationError("This user is already assigned to another hub.")
            return value
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")


    def create(self, validated_data):
        admin_id = validated_data.pop("hub_admin", None)
        hub = Hub.objects.create(**validated_data)

        if admin_id:
            user = User.objects.get(id=admin_id)

            # Remove existing hub_admin membership if any
            HubMembership.objects.filter(user=user, role="hub_admin").delete()

            # Create new membership as hub_admin
            HubMembership.objects.create(
                user=user,
                hub=hub,
                role="hub_admin",
                status="active"
            )

        return hub


    def update(self, instance, validated_data):
        admin_id = validated_data.pop("hub_admin", None)
        instance = super().update(instance, validated_data)

        if admin_id is not None:
            # Clear old admin
            HubMembership.objects.filter(hub=instance, role="hub_admin").delete()

            if admin_id:
                user = User.objects.get(id=admin_id)

                # Remove any existing hub_admin membership for this user
                HubMembership.objects.filter(user=user, role="hub_admin").delete()

                # Assign new admin
                HubMembership.objects.create(
                    user=user,
                    hub=instance,
                    role="hub_admin",
                    status="active"
                )

        return instance



class HubMembershipRequestSerializer(serializers.ModelSerializer):
    """For users to request hub membership"""
    
    class Meta:
        model = HubMembership
        fields = ['hub', 'reason']
        
    def validate_hub(self, value):
        """Ensure hub is active"""
        if not value.is_active:
            raise serializers.ValidationError("This hub is not accepting new members.")
        return value
    
    def validate(self, attrs):
        """Check if user already has membership in this hub"""
        user = self.context['request'].user
        hub = attrs.get('hub')
        
        existing_membership = HubMembership.objects.filter(
            user=user, 
            hub=hub
        ).first()
        
        if existing_membership:
            if existing_membership.status == 'active':
                raise serializers.ValidationError("You are already a member of this hub.")
            elif existing_membership.status == 'pending':
                raise serializers.ValidationError("Your membership request is still pending.")
            elif existing_membership.status == 'rejected':
                # Allow re-application after rejection
                pass
        
        return attrs
    
    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        validated_data['role'] = user.role  # Use user's system role as default
        
        # If re-applying after rejection, update existing record
        existing = HubMembership.objects.filter(
            user=user,
            hub=validated_data['hub']
        ).first()
        
        if existing:
            existing.status = 'pending'
            existing.reason = validated_data.get('reason', '')
            existing.requested_at = timezone.now()
            existing.save()
            return existing
        
        return super().create(validated_data)

class HubMembershipSerializer(serializers.ModelSerializer):
    """Full membership details"""
    user = serializers.SerializerMethodField()
    hub = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = HubMembership
        fields = [
            'id', 'user', 'hub', 'role', 'status', 'reason', 'notes',
            'requested_at', 'approved_at', 'approved_by_name'
        ]
        read_only_fields = ['id', 'requested_at', 'approved_at', 'approved_by_name']
    
    def get_user(self, obj):
        return {
            'id': str(obj.user.id),
            'name': f"{obj.user.first_name} {obj.user.last_name}".strip(),
            'phone_number': obj.user.phone_number,
        }
    
    def get_hub(self, obj):
        return {
            'id': str(obj.hub.id),
            'name': obj.hub.name,
            'location': obj.hub.location,
        }
    
    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return f"{obj.approved_by.first_name} {obj.approved_by.last_name}".strip()
        return None

class HubMembershipApprovalSerializer(serializers.ModelSerializer):
    """For admins to approve/reject memberships"""
    
    class Meta:
        model = HubMembership
        fields = ['status', 'role', 'notes']
    
    def validate_status(self, value):
        if value not in ['active', 'rejected']:
            raise serializers.ValidationError("Status must be 'active' or 'rejected'")
        return value
    
    def update(self, instance, validated_data):
        user = self.context['request'].user
        instance.approved_by = user
        instance.approved_at = timezone.now()
        return super().update(instance, validated_data)

class UserHubListSerializer(serializers.ModelSerializer):
    """List of hubs a user belongs to"""
    membership_role = serializers.SerializerMethodField()
    membership_status = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Hub
        fields = ['id', 'name', 'location', 'membership_role', 'membership_status', 'member_count']
    
    def get_membership_role(self, obj):
        user = self.context['request'].user
        membership = user.hub_memberships.filter(hub=obj).first()
        return membership.role if membership else None
    
    def get_membership_status(self, obj):
        user = self.context['request'].user
        membership = user.hub_memberships.filter(hub=obj).first()
        return membership.status if membership else None
    
    def get_member_count(self, obj):
        return obj.memberships.filter(status='active').count()