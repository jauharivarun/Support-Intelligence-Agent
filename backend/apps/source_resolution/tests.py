"""Source resolution and authorization acceptance tests (Doc 08)."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.orders.models import Order
from apps.source_resolution.engine import (
    DecisionStatus,
    SourceCandidate,
    resolve_sources,
)
from apps.users.models import Role

User = get_user_model()


def cand(**kwargs):
    defaults = dict(
        document_id=1,
        name="Doc",
        source_type="POLICY_SOP",
        status="CURRENT",
        authority_level=80,
        scope_type="GENERAL",
        account_id=None,
        effective_date=date(2026, 1, 1),
        expiry_date=None,
        explicit_override_domains=[],
        domains=["CANCELLATION"],
        content_snippet="",
    )
    defaults.update(kwargs)
    return SourceCandidate(**defaults)


class SourceResolutionTests(TestCase):
    def test_agreement_overrides_sop(self):
        agreement = cand(
            document_id=1,
            name="Northstar Agreement",
            source_type="CUSTOMER_AGREEMENT",
            status="ACTIVE",
            authority_level=100,
            scope_type="CUSTOMER_SPECIFIC",
            account_id="ACCT-001",
            explicit_override_domains=["CANCELLATION"],
        )
        sop = cand(
            document_id=2,
            name="Cancellation SOP",
            authority_level=80,
            domains=["CANCELLATION"],
        )
        result = resolve_sources(
            [agreement, sop],
            domain="CANCELLATION",
            account_id="ACCT-001",
            reference_date=date(2026, 8, 16),
        )
        self.assertEqual(result.status, DecisionStatus.OVERRIDE_APPLIED)
        self.assertEqual(result.primary_source.name, "Northstar Agreement")

    def test_deprecated_excluded(self):
        deprecated = cand(
            name="Policy v2",
            status="DEPRECATED",
            authority_level=0,
            source_type="DEPRECATED",
        )
        current = cand(name="Policy v3", status="CURRENT", authority_level=80, domains=["SLA"])
        result = resolve_sources(
            [deprecated, current],
            domain="SLA",
            account_id=None,
            reference_date=date(2026, 8, 16),
        )
        self.assertEqual(result.status, DecisionStatus.RESOLVED)
        self.assertEqual(result.primary_source.name, "Policy v3")
        self.assertTrue(any(e["reason"] == "deprecated_or_zero_authority" for e in result.excluded_sources))

    def test_historical_context_not_authority(self):
        hist = cand(
            name="Old ticket note",
            source_type="HISTORICAL_CONTEXT",
            status="CONTEXT_ONLY",
            authority_level=20,
        )
        product = cand(
            name="Product Guide",
            source_type="PRODUCT_DOC",
            status="CURRENT",
            authority_level=70,
            scope_type="PRODUCT",
            domains=["PRODUCT"],
        )
        result = resolve_sources(
            [hist, product],
            domain="PRODUCT",
            reference_date=date(2026, 8, 16),
        )
        self.assertEqual(result.status, DecisionStatus.RESOLVED)
        self.assertEqual(result.primary_source.name, "Product Guide")

    def test_missing_information(self):
        result = resolve_sources(
            [],
            missing_facts=["carrier_fault"],
            reference_date=date(2026, 8, 16),
        )
        self.assertEqual(result.status, DecisionStatus.NEEDS_MORE_INFORMATION)

    def test_human_judgment(self):
        result = resolve_sources([], requires_human_judgment=True)
        self.assertEqual(result.status, DecisionStatus.HUMAN_JUDGMENT_REQUIRED)

    def test_genuine_conflict_same_authority(self):
        a = cand(document_id=1, name="Policy A", authority_level=80, conclusion="FEE")
        b = cand(document_id=2, name="Policy B", authority_level=80, conclusion="NO_FEE")
        result = resolve_sources(
            [a, b],
            domain="CANCELLATION",
            conclusions={"Policy A": "FEE", "Policy B": "NO_FEE"},
            reference_date=date(2026, 8, 16),
        )
        self.assertEqual(result.status, DecisionStatus.CONFLICT_REQUIRES_VERIFICATION)

    def test_lumenworks_agreement_does_not_override_cancellation(self):
        agreement = cand(
            document_id=6,
            name="LumenWorks Service Agreement",
            source_type="CUSTOMER_AGREEMENT",
            status="ACTIVE",
            authority_level=100,
            scope_type="CUSTOMER_SPECIFIC",
            account_id="ACCT-002",
            explicit_override_domains=["SERVICE_CREDIT", "SLA", "SUPPORT"],
            domains=["CANCELLATION", "SERVICE_CREDIT", "SLA"],
        )
        sop = cand(document_id=3, name="Cancellation SOP", authority_level=80, domains=["CANCELLATION"])
        result = resolve_sources(
            [agreement, sop],
            domain="CANCELLATION",
            account_id="ACCT-002",
            reference_date=date(2026, 8, 16),
        )
        self.assertEqual(result.status, DecisionStatus.RESOLVED)
        self.assertEqual(result.primary_source.name, "Cancellation SOP")

    def test_lumenworks_agreement_overrides_service_credit(self):
        agreement = cand(
            document_id=6,
            name="LumenWorks Service Agreement",
            source_type="CUSTOMER_AGREEMENT",
            status="ACTIVE",
            authority_level=100,
            scope_type="CUSTOMER_SPECIFIC",
            account_id="ACCT-002",
            explicit_override_domains=["SERVICE_CREDIT", "SLA", "SUPPORT"],
            domains=["CANCELLATION", "SERVICE_CREDIT"],
        )
        sop = cand(document_id=3, name="Cancellation SOP", authority_level=80, domains=["SERVICE_CREDIT"])
        result = resolve_sources(
            [agreement, sop],
            domain="SERVICE_CREDIT",
            account_id="ACCT-002",
            reference_date=date(2026, 8, 16),
        )
        self.assertEqual(result.status, DecisionStatus.OVERRIDE_APPLIED)
        self.assertEqual(result.primary_source.name, "LumenWorks Service Agreement")

    def test_other_account_agreement_not_applicable(self):
        ns = cand(
            document_id=5,
            name="Northstar Agreement",
            source_type="CUSTOMER_AGREEMENT",
            status="ACTIVE",
            authority_level=100,
            scope_type="CUSTOMER_SPECIFIC",
            account_id="ACCT-001",
            explicit_override_domains=["CANCELLATION"],
        )
        sop = cand(document_id=3, name="Cancellation SOP", authority_level=80)
        result = resolve_sources(
            [ns, sop],
            domain="CANCELLATION",
            account_id="ACCT-002",
            reference_date=date(2026, 8, 16),
        )
        self.assertEqual(result.primary_source.name, "Cancellation SOP")
        self.assertTrue(any(e["reason"] == "not_applicable" for e in result.excluded_sources))

    def test_future_effective_date_excluded(self):
        future = cand(
            name="Future SOP",
            effective_date=date(2027, 1, 1),
            authority_level=90,
        )
        current = cand(name="Current SOP", effective_date=date(2026, 1, 1), authority_level=80)
        result = resolve_sources(
            [future, current],
            domain="CANCELLATION",
            reference_date=date(2026, 8, 16),
        )
        self.assertEqual(result.primary_source.name, "Current SOP")
        self.assertTrue(any(e["reason"] == "temporally_invalid" for e in result.excluded_sources))


class AuthorizationAPITests(TestCase):
    def setUp(self):
        self.a1 = Account.objects.create(account_code="ACCT-001", name="Northstar")
        self.a2 = Account.objects.create(account_code="ACCT-002", name="LumenWorks")
        Order.objects.create(order_id="ORD-1001", account=self.a1, status="BOOKED")
        Order.objects.create(order_id="ORD-2001", account=self.a2, status="BOOKED")
        self.customer = User.objects.create_user(
            username="northstar@demo.local",
            email="northstar@demo.local",
            password="demo1234",
            role=Role.CUSTOMER,
            account=self.a1,
            name="Northstar",
        )
        self.client = APIClient()

    def test_customer_cannot_access_other_account_order(self):
        self.client.force_authenticate(user=self.customer)
        resp = self.client.get("/api/orders/ORD-2001/")
        self.assertEqual(resp.status_code, 404)

    def test_customer_can_access_own_order(self):
        self.client.force_authenticate(user=self.customer)
        resp = self.client.get("/api/orders/ORD-1001/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["order_id"], "ORD-1001")

    def test_customer_ticket_list_scoped(self):
        from apps.tickets.models import Ticket
        from django.utils import timezone

        Ticket.objects.create(
            ticket_id="TKT-501",
            account=self.a1,
            created_at=timezone.now(),
            status="open",
            subject="x",
        )
        Ticket.objects.create(
            ticket_id="TKT-502",
            account=self.a2,
            created_at=timezone.now(),
            status="open",
            subject="y",
        )
        self.client.force_authenticate(user=self.customer)
        resp = self.client.get("/api/tickets/")
        self.assertEqual(resp.status_code, 200)
        ids = [t["ticket_id"] for t in resp.data]
        self.assertIn("TKT-501", ids)
        self.assertNotIn("TKT-502", ids)
