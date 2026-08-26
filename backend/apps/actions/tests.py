from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.actions.models import PendingAction, PendingActionStatus
from apps.users.models import Role

User = get_user_model()


class PendingActionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="support@demo.local",
            email="support@demo.local",
            password="demo1234",
            role=Role.INTERNAL_SUPPORT,
            name="Support",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.action = PendingAction.objects.create(
            user=self.user,
            action_type="CREATE_FOLLOW_UP",
            payload={"title": "Call customer", "description": "Verify fault"},
            reason="Verify fault",
            status=PendingActionStatus.AWAITING_CONFIRMATION,
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    def test_confirm_executes(self):
        resp = self.client.post(f"/api/actions/{self.action.id}/confirm/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "EXECUTED")
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, PendingActionStatus.EXECUTED)

    def test_cancel(self):
        resp = self.client.post(f"/api/actions/{self.action.id}/cancel/")
        self.assertEqual(resp.status_code, 200)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, PendingActionStatus.CANCELLED)

    def test_expired_blocked(self):
        self.action.expires_at = timezone.now() - timedelta(minutes=1)
        self.action.save()
        resp = self.client.post(f"/api/actions/{self.action.id}/confirm/")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["status"], "EXPIRED")
