from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.documents.models import DocumentStatus, ScopeType, SourceDocument, SourceType
from apps.users.models import Role

User = get_user_model()


class DocumentListApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin@demo.local",
            email="admin@demo.local",
            password="demo1234",
            role=Role.ADMIN,
        )
        self.acct = Account.objects.create(account_code="ACCT-001", name="Northstar")
        SourceDocument.objects.create(
            name="ParcelPilot Support Policy v3",
            source_type=SourceType.POLICY_SOP,
            status=DocumentStatus.CURRENT,
            authority_level=80,
            scope_type=ScopeType.GENERAL,
        )
        SourceDocument.objects.create(
            name="Northstar Logistics Enterprise Agreement",
            source_type=SourceType.CUSTOMER_AGREEMENT,
            status=DocumentStatus.ACTIVE,
            authority_level=100,
            scope_type=ScopeType.CUSTOMER_SPECIFIC,
            account=self.acct,
            original_filename="05_Northstar.pdf",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_admin_can_list_documents(self):
        resp = self.client.get("/api/documents/")
        self.assertEqual(resp.status_code, 200)
        names = [d["name"] for d in resp.data]
        self.assertIn("ParcelPilot Support Policy v3", names)
        self.assertIn("Northstar Logistics Enterprise Agreement", names)
        northstar = next(d for d in resp.data if "Northstar" in d["name"])
        self.assertEqual(northstar["account_code"], "ACCT-001")
        self.assertEqual(northstar["original_filename"], "05_Northstar.pdf")
