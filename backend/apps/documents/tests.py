from datetime import date
import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import Account
from apps.agent.tools import document_search
from apps.documents.embeddings import embed_texts
from apps.documents.models import DocumentChunk, DocumentStatus, ScopeType, SourceDocument, SourceType
from apps.users.models import Role
from apps.users.permissions import user_context

User = get_user_model()


def _add_doc(**kwargs):
    content = kwargs.pop("content")
    domains = kwargs.pop("domains", [])
    doc = SourceDocument.objects.create(**kwargs)
    embedding = embed_texts([content])[0]
    DocumentChunk.objects.create(
        document=doc,
        content=content,
        embedding=embedding,
        domain=domains[0] if domains else "",
        metadata={"domains": domains},
        chunk_effective_date=doc.effective_date,
        chunk_expiry_date=doc.expiry_date,
    )
    return doc


@override_settings(USE_MOCK_EMBEDDINGS=True, DATASET_REFERENCE_TIME="2026-08-16T11:00:00+05:30")
class DocumentRetrievalRankingTests(TestCase):
    def setUp(self):
        self.ns = Account.objects.create(account_code="ACCT-001", name="Northstar")
        self.lw = Account.objects.create(account_code="ACCT-002", name="LumenWorks")
        cancel_text = (
            "Cancellation of BOOKED shipments: no fee within 30 minutes of booking; "
            "after that INR 250 applies unless a customer agreement waives the fee."
        )
        _add_doc(
            name="Cancellation & Service Credit SOP v4",
            source_type=SourceType.POLICY_SOP,
            status=DocumentStatus.CURRENT,
            authority_level=80,
            scope_type=ScopeType.GENERAL,
            effective_date=date(2026, 6, 15),
            content=cancel_text,
            domains=["CANCELLATION"],
        )
        _add_doc(
            name="Northstar Logistics Enterprise Agreement",
            source_type=SourceType.CUSTOMER_AGREEMENT,
            status=DocumentStatus.ACTIVE,
            authority_level=100,
            scope_type=ScopeType.CUSTOMER_SPECIFIC,
            account=self.ns,
            effective_date=date(2026, 1, 1),
            expiry_date=date(2026, 12, 31),
            explicit_override_domains=["CANCELLATION", "SLA", "SUPPORT"],
            content=(
                "Northstar cancellation: BOOKED shipments may be cancelled before pickup "
                "with no cancellation fee. This waives the SOP INR 250 fee."
            ),
            domains=["CANCELLATION", "SLA"],
        )
        _add_doc(
            name="LumenWorks Service Agreement",
            source_type=SourceType.CUSTOMER_AGREEMENT,
            status=DocumentStatus.ACTIVE,
            authority_level=100,
            scope_type=ScopeType.CUSTOMER_SPECIFIC,
            account=self.lw,
            effective_date=date(2026, 3, 1),
            explicit_override_domains=["SERVICE_CREDIT", "SLA", "SUPPORT"],
            content="LumenWorks service credit terms. Cancellation fees follow the standard SOP.",
            domains=["CANCELLATION", "SERVICE_CREDIT"],
        )
        _add_doc(
            name="Test Policy Update Version 2",
            source_type=SourceType.POLICY_SOP,
            status=DocumentStatus.CURRENT,
            authority_level=90,
            scope_type=ScopeType.GENERAL,
            effective_date=date(2026, 8, 1),
            explicit_override_domains=[],
            content=(
                "Updated default cancellation: after carrier assignment but before pickup, "
                "fee is 2% of order value maximum INR 750. "
                "Default maximum service credit: INR 1000 or 15% of eligible order value, whichever is lower. "
                "Cancellation requests above INR 50000 require Priority Review before finalizing the fee."
            ),
            domains=["CANCELLATION", "SERVICE_CREDIT"],
        )
        _add_doc(
            name="ParcelPilot Support Policy v2",
            source_type=SourceType.DEPRECATED,
            status=DocumentStatus.DEPRECATED,
            authority_level=0,
            scope_type=ScopeType.GENERAL,
            effective_date=date(2025, 1, 1),
            expiry_date=date(2026, 4, 30),
            content="Deprecated cancellation policy v2 should never rank for current decisions.",
            domains=["CANCELLATION"],
        )
        self.ns_user = User.objects.create_user(
            username="northstar@demo.local",
            email="northstar@demo.local",
            password="demo1234",
            role=Role.CUSTOMER,
            account=self.ns,
        )
        self.lw_user = User.objects.create_user(
            username="lumenworks@demo.local",
            email="lumenworks@demo.local",
            password="demo1234",
            role=Role.CUSTOMER,
            account=self.lw,
        )
        self.support = User.objects.create_user(
            username="support@demo.local",
            email="support@demo.local",
            password="demo1234",
            role=Role.INTERNAL_SUPPORT,
        )

    def test_northstar_ranks_agreement_over_sop(self):
        result = document_search(
            user_context(self.ns_user),
            "Northstar BOOKED cancellation fee waiver",
            domain="CANCELLATION",
        )
        names = [r["document_name"] for r in result["results"]]
        self.assertIn("Northstar Logistics Enterprise Agreement", names)
        self.assertNotIn("ParcelPilot Support Policy v2", names)
        self.assertEqual(result["source_resolution"]["status"], "OVERRIDE_APPLIED")
        self.assertEqual(
            result["source_resolution"]["primary_source"]["name"],
            "Northstar Logistics Enterprise Agreement",
        )

    def test_lumenworks_cannot_see_northstar_agreement(self):
        result = document_search(
            user_context(self.lw_user),
            "What is my cancellation policy?",
            domain="CANCELLATION",
        )
        names = [r["document_name"] for r in result["results"]]
        self.assertNotIn("Northstar Logistics Enterprise Agreement", names)
        self.assertEqual(
            result["source_resolution"]["primary_source"]["name"],
            "Test Policy Update Version 2",
        )
        labels = {r["document_name"]: r.get("label") for r in result["results"]}
        self.assertEqual(labels.get("Test Policy Update Version 2"), "ParcelPilot global policy")

    def test_lumenworks_asking_about_northstar_is_denied(self):
        result = document_search(
            user_context(self.lw_user),
            "What are Northstar customer cancellation policies?",
        )
        self.assertEqual(result.get("error"), "AUTHORIZATION_DENIED")

    def test_rewritten_search_still_denied_from_original_user_message(self):
        ctx = user_context(self.ns_user)
        ctx["user_message"] = "I want to know cancellation policies for lumen works"
        result = document_search(ctx, "cancellation policies")
        self.assertEqual(result.get("error"), "AUTHORIZATION_DENIED")

    def test_internal_infers_northstar_account_for_resolution(self):
        result = document_search(
            user_context(self.support),
            "What is the cancellation policy for Northstar?",
        )
        self.assertNotEqual(result.get("error"), "AUTHORIZATION_DENIED")
        self.assertEqual(result.get("account_id"), "ACCT-001")
        self.assertEqual(
            result["source_resolution"]["primary_source"]["name"],
            "Northstar Logistics Enterprise Agreement",
        )

    def test_internal_current_turn_overrides_stale_account_id(self):
        ctx = user_context(self.support)
        ctx["user_message"] = "What is the Northstar agreement cancellation fee waiver?"
        result = document_search(
            ctx,
            "cancellation fee waiver",
            account_id="ACCT-004",
        )
        self.assertNotEqual(result.get("error"), "AUTHORIZATION_DENIED")
        self.assertEqual(result.get("account_id"), "ACCT-001")
        self.assertEqual(
            result["source_resolution"]["primary_source"]["name"],
            "Northstar Logistics Enterprise Agreement",
        )

    def test_internal_historical_claim_query_still_applies_northstar_override(self):
        ctx = user_context(self.support)
        ctx["user_message"] = (
            "A previous agent told Northstar that a BOOKED cancel 90 minutes "
            "after booking costs ₹250. Is that still true?"
        )
        result = document_search(ctx, "Northstar BOOKED 90 minutes 250")
        self.assertEqual(result.get("domain"), "CANCELLATION")
        self.assertEqual(result.get("account_id"), "ACCT-001")
        self.assertEqual(result["source_resolution"]["status"], "OVERRIDE_APPLIED")
        self.assertEqual(
            result["source_resolution"]["primary_source"]["name"],
            "Northstar Logistics Enterprise Agreement",
        )
        self.assertIn("not still true", result.get("decision_guidance", "").lower())

    def test_global_cancel_defaults_prefer_higher_authority_v2(self):
        result = document_search(
            user_context(self.support),
            "What is the default cancellation fee for a BOOKED shipment after carrier assignment but before pickup?",
            domain="CANCELLATION",
        )
        self.assertIsNone(result.get("account_id"))
        names = [r["document_name"] for r in result["results"]]
        self.assertNotIn("Northstar Logistics Enterprise Agreement", names)
        self.assertNotIn("LumenWorks Service Agreement", names)
        self.assertEqual(
            result["source_resolution"]["primary_source"]["name"],
            "Test Policy Update Version 2",
        )
        self.assertEqual(result["source_resolution"]["primary_source"]["authority_level"], 90)
        cite = [c["name"] for c in result.get("citation_sources") or []]
        self.assertEqual(cite, ["Test Policy Update Version 2"])

    def test_invalid_llm_domain_still_infers_cancellation(self):
        """Models often pass source_type labels; those must not wipe applicable sources."""
        result = document_search(
            user_context(self.support),
            "What is the default cancellation fee after carrier assignment?",
            domain="POLICY_SOP",
        )
        self.assertEqual(result.get("domain"), "CANCELLATION")
        self.assertEqual(
            result["source_resolution"]["primary_source"]["name"],
            "Test Policy Update Version 2",
        )
        self.assertEqual(
            [c["name"] for c in result.get("citation_sources") or []],
            ["Test Policy Update Version 2"],
        )

    def test_high_value_cancel_surfaces_priority_review_clause(self):
        result = document_search(
            user_context(self.support),
            "A customer wants to cancel a ₹75,000 BOOKED shipment. What fee applies?",
            domain="CANCELLATION",
        )
        self.assertEqual(
            result["source_resolution"]["primary_source"]["name"],
            "Test Policy Update Version 2",
        )
        joined = " ".join((r.get("content") or "") for r in result["results"]).lower()
        flat = re.sub(r"\s+", "", joined)
        self.assertIn("priorityreview", flat)
        self.assertIn("priority review", result.get("decision_guidance", "").lower())

    def test_global_service_credit_defaults_prefer_v2(self):
        result = document_search(
            user_context(self.support),
            "What is the default maximum service credit under the current policy?",
            domain="SERVICE_CREDIT",
        )
        self.assertEqual(
            result["source_resolution"]["primary_source"]["name"],
            "Test Policy Update Version 2",
        )

    def test_northstar_scoped_cancel_still_overrides_v2(self):
        result = document_search(
            user_context(self.support),
            "Can ORD-1001 be cancelled without a fee for Northstar?",
            domain="CANCELLATION",
            account_id="ACCT-001",
        )
        self.assertEqual(result.get("account_id"), "ACCT-001")
        self.assertEqual(result["source_resolution"]["status"], "OVERRIDE_APPLIED")
        self.assertEqual(
            result["source_resolution"]["primary_source"]["name"],
            "Northstar Logistics Enterprise Agreement",
        )
