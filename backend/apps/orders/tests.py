from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Account
from apps.agent.tools import calculate_cancellation_fee, get_order
from apps.orders.models import Order
from apps.users.models import Role
from apps.users.permissions import user_context

User = get_user_model()


class ToolAuthzTests(TestCase):
    def setUp(self):
        self.a1 = Account.objects.create(account_code="ACCT-001", name="Northstar")
        self.a2 = Account.objects.create(account_code="ACCT-002", name="Lumen")
        Order.objects.create(order_id="ORD-2001", account=self.a2, status="BOOKED")
        self.user = User.objects.create_user(
            username="c@demo.local",
            email="c@demo.local",
            password="demo1234",
            role=Role.CUSTOMER,
            account=self.a1,
        )

    def test_get_order_denied_cross_account(self):
        ctx = user_context(self.user)
        result = get_order(ctx, "ORD-2001")
        self.assertEqual(result.get("error"), "AUTHORIZATION_DENIED")


class CancellationCalcTests(TestCase):
    def setUp(self):
        self.a1 = Account.objects.create(account_code="ACCT-001", name="Northstar", plan="Enterprise")
        self.a3 = Account.objects.create(account_code="ACCT-003", name="Beacon", plan="Standard")
        self.user = User.objects.create_user(
            username="support@demo.local",
            email="support@demo.local",
            password="demo1234",
            role=Role.INTERNAL_SUPPORT,
        )
        booked = timezone.now() - timedelta(hours=2)
        Order.objects.create(
            order_id="ORD-1001",
            account=self.a1,
            status="BOOKED",
            booked_at=booked,
            cancellation_requested_at=timezone.now(),
            shipment_fee_inr=Decimal("4200"),
        )
        Order.objects.create(
            order_id="ORD-3001",
            account=self.a3,
            status="BOOKED",
            booked_at=timezone.now() - timedelta(minutes=10),
            cancellation_requested_at=timezone.now(),
            shipment_fee_inr=Decimal("1200"),
        )

    def test_northstar_override_no_fee(self):
        from apps.documents.models import SourceDocument

        SourceDocument.objects.create(
            name="Northstar Logistics Enterprise Agreement",
            source_type="CUSTOMER_AGREEMENT",
            status="ACTIVE",
            authority_level=100,
            scope_type="CUSTOMER_SPECIFIC",
            account=self.a1,
            explicit_override_domains=["CANCELLATION", "SLA", "SUPPORT"],
        )
        ctx = user_context(self.user)
        result = calculate_cancellation_fee(ctx, "ORD-1001")
        self.assertEqual(result["fee_inr"], 0)
        self.assertEqual(result["decision_status"], "OVERRIDE_APPLIED")

    def test_sop_within_30_min_no_fee(self):
        ctx = user_context(self.user)
        result = calculate_cancellation_fee(ctx, "ORD-3001")
        self.assertEqual(result["fee_inr"], 0)
        self.assertEqual(result["rule"], "SOP_NO_FEE_WITHIN_30_MIN")
