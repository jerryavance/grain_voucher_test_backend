from django.test import TestCase
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from authentication.models import GrainUser
from .models import Hub
from utils.permissions import IsSuperAdmin
from django.contrib.auth import get_user_model

User = get_user_model()

class HubViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.hub = Hub.objects.create(name="Test Hub", slug="test-hub", location="Kampala")
        self.super_admin = User.objects.create_user(
            phone_number="+256772000000",
            role="super_admin"
        )
        self.hub_admin = User.objects.create_user(
            phone_number="+256772000001",
            role="hub_admin",
            hub=self.hub
        )

    def test_create_hub_super_admin(self):
        self.client.force_authenticate(self.super_admin)
        data = {"name": "New Hub", "slug": "new-hub", "location": "Gulu"}
        response = self.client.post(reverse("hubs:hub-list"), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Hub.objects.filter(slug="new-hub").exists())

    def test_create_hub_unauthorized(self):
        self.client.force_authenticate(self.hub_admin)
        data = {"name": "New Hub", "slug": "new-hub", "location": "Gulu"}
        response = self.client.post(reverse("hubs:hub-list"), data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_assign_hub_admin(self):
        self.client.force_authenticate(self.super_admin)
        new_admin = User.objects.create_user(
            phone_number="+256772000005",
            role="hub_admin"
        )
        data = {"user_id": str(new_admin.id)}
        response = self.client.post(
            reverse("hubs:hub-assign-admin", kwargs={"pk": self.hub.id}),
            data
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_admin.refresh_from_db()
        self.assertEqual(new_admin.hub, self.hub)


#pytest hubs/tests.py