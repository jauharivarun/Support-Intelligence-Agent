from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.orders.models import Order
from apps.users.models import Role
from django.utils import timezone
from datetime import timedelta
from apps.agent.tools import annotate_tool_result


class ToolAnnotationTests(TestCase):
    def test_successful_search_is_not_marked_failed(self):
        payload = annotate_tool_result(
            "document_search",
            {
                "query": "cancellations shipping returns",
                "results": [
                    {
                        "document_name": "Cancellation SOP",
                        "content": "BOOKED orders may be cancelled. After pickup use return-to-origin.",
                    }
                ],
            },
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["retrieval_status"], "ok")
        self.assertIn("cancellations", payload["topics_found_in_documents"])
        self.assertIn("shipping", payload["topics_not_in_knowledge_base"])


class ToolSourceIngestTests(TestCase):
    def test_search_hits_become_named_sources(self):
        from apps.agent.orchestrator import _ingest_tool_sources

        collected: list[dict] = []
        status = _ingest_tool_sources(
            collected,
            {
                "results": [{"document_name": "Cancellation & Service Credit SOP v4"}],
                "source_resolution": {
                    "status": "OVERRIDE_APPLIED",
                    "primary_source": {"name": "Northstar Logistics Enterprise Agreement"},
                },
            },
        )
        names = {s["name"] for s in collected}
        self.assertEqual(status, "OVERRIDE_APPLIED")
        self.assertIn("Cancellation & Service Credit SOP v4", names)
        self.assertIn("Northstar Logistics Enterprise Agreement", names)

    def test_tool_error_is_marked_failed(self):
        payload = annotate_tool_result("document_search", {"error": "timeout"})
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["retrieval_status"], "tool_error")

User = get_user_model()


@override_settings(OPENAI_API_KEY="")
class AgentChatTests(TestCase):
    def setUp(self):
        self.acct = Account.objects.create(account_code="ACCT-001", name="Northstar", plan="Enterprise")
        self.user = User.objects.create_user(
            username="northstar@demo.local",
            email="northstar@demo.local",
            password="demo1234",
            role=Role.CUSTOMER,
            account=self.acct,
        )
        booked = timezone.now() - timedelta(hours=2)
        Order.objects.create(
            order_id="ORD-1001",
            account=self.acct,
            status="BOOKED",
            booked_at=booked,
            cancellation_requested_at=timezone.now(),
            shipment_fee_inr=4200,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_capability_question_returns_samples(self):
        resp = self.client.post(
            "/api/agent/chat/",
            {"message": "What can you show me?"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        answer = resp.data["answer"]
        self.assertIn("Try asking:", answer)
        self.assertIn("ORD-1001", answer)
        self.assertNotIn("Based on retrieved sources", answer)
        self.assertEqual(resp.data["decision_status"], None)
        self.assertEqual(resp.data["tool_activity"], [])
        self.assertEqual(resp.data["sources"], [])

    def test_cancellation_answer_is_conversational(self):
        resp = self.client.post(
            "/api/agent/chat/",
            {"message": "Can ORD-1001 be cancelled without a fee?"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        answer = resp.data["answer"]
        self.assertNotIn("cancellable=", answer)
        self.assertNotIn("Rule=", answer)
        self.assertIn("ord-1001", answer.lower())

    def test_p1_support_target_answer(self):
        resp = self.client.post(
            "/api/agent/chat/",
            {"message": "What is the P1 support response target for my account?"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        answer = resp.data["answer"]
        self.assertIn("15 minutes", answer)
        self.assertNotIn("Based on retrieved sources", answer)

    def test_chat_returns_answer(self):
        resp = self.client.post(
            "/api/agent/chat/",
            {"message": "Can ORD-1001 be cancelled without a fee?"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("answer", resp.data)
        self.assertIn("decision_status", resp.data)

    def test_service_credit_states_booked_status(self):
        resp = self.client.post(
            "/api/agent/chat/",
            {"message": "Am I eligible for a service credit on ORD-1001?"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        answer = resp.data["answer"].lower()
        self.assertIn("booked", answer)
        self.assertNotIn("unable to retrieve", answer)

    def test_swiftship_booked_mentions_ki211(self):
        resp = self.client.post(
            "/api/agent/chat/",
            {"message": "Why does my SwiftShip order still show BOOKED after the driver picked it up?"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        answer = resp.data["answer"]
        self.assertIn("KI-211", answer)
        self.assertIn("20 minutes", answer)
        self.assertNotIn("technical glitch", answer.lower())


@override_settings(OPENAI_API_KEY="")
class InternalSupportChatTests(TestCase):
    def setUp(self):
        Account.objects.create(account_code="ACCT-001", name="Northstar", plan="Enterprise")
        self.user = User.objects.create_user(
            username="support@demo.local",
            email="support@demo.local",
            password="demo1234",
            role=Role.INTERNAL_SUPPORT,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_p1_for_acct_001_uses_agreement_not_default_policy(self):
        resp = self.client.post(
            "/api/agent/chat/",
            {"message": "What is the P1 target for ACCT-001?"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        answer = resp.data["answer"]
        self.assertIn("15 minutes", answer)
        self.assertNotIn("30 minutes", answer)
        sources = " ".join(s.get("name") or "" for s in resp.data.get("sources") or [])
        self.assertIn("Northstar", sources)


class MarkdownNormalizeTests(TestCase):
    def test_glued_and_inline_hashes_become_headings(self):
        from apps.agent.formatters import normalize_answer_markdown, scrub_user_answer

        raw = "Here is the policy.###Cancellation\n###Fees apply after pickup"
        out = normalize_answer_markdown(raw)
        self.assertIn("### Cancellation", out)
        self.assertIn("### Fees apply after pickup", out)
        self.assertNotIn("###Cancellation", out)
        self.assertEqual(normalize_answer_markdown("#######\nStill readable"), "Still readable")
        scrubbed = scrub_user_answer("#Cancellation Policy\nBOOKED orders may be cancelled.")
        self.assertTrue(scrubbed.startswith("# Cancellation Policy"))


@override_settings(OPENAI_API_KEY="")
class OfflineDoesNotInventOrderTests(TestCase):
    def setUp(self):
        self.acct = Account.objects.create(account_code="ACCT-001", name="Northstar", plan="Enterprise")
        self.user = User.objects.create_user(
            username="northstar@demo.local",
            email="northstar@demo.local",
            password="demo1234",
            role=Role.CUSTOMER,
            account=self.acct,
        )
        booked = timezone.now() - timedelta(hours=2)
        Order.objects.create(
            order_id="ORD-1001",
            account=self.acct,
            status="BOOKED",
            booked_at=booked,
            cancellation_requested_at=timezone.now(),
            shipment_fee_inr=4200,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_historical_advice_is_not_mapped_to_ord_1001(self):
        resp = self.client.post(
            "/api/agent/chat/",
            {
                "message": (
                    "A previous agent told Northstar that a BOOKED cancel 90 minutes "
                    "after booking costs ₹250. Is that still true?"
                )
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        answer = resp.data["answer"]
        self.assertNotIn("Yes — you can cancel ORD-1001", answer)

    def test_generic_cancellation_policy_is_not_mapped_to_ord_1001(self):
        resp = self.client.post(
            "/api/agent/chat/",
            {"message": "What is the cancellation policy?"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Yes — you can cancel ORD-1001", resp.data["answer"])


@override_settings(OPENAI_API_KEY="sk-test-not-used")
class LiveAgentUsesLlmPathTests(TestCase):
    def setUp(self):
        self.acct = Account.objects.create(account_code="ACCT-001", name="Northstar", plan="Enterprise")
        self.user = User.objects.create_user(
            username="support@demo.local",
            email="support@demo.local",
            password="demo1234",
            role=Role.INTERNAL_SUPPORT,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_openai_path_runs_instead_of_canned_maps(self):
        from unittest.mock import patch

        with patch("apps.agent.orchestrator._run_openai") as mock_run:
            mock_run.return_value = {
                "answer": "Grounded from retrieved documents, not a canned map.",
                "decision_status": None,
                "sources": [{"name": "Cancellation & Service Credit SOP v4"}],
                "tool_activity": ["Searching applicable policies"],
                "pending_action": None,
                "mode": "openai",
            }
            resp = self.client.post(
                "/api/agent/chat/",
                {
                    "message": (
                        "A previous agent told Northstar that a BOOKED cancel 90 minutes "
                        "after booking costs ₹250. Is that still true?"
                    )
                },
                format="json",
            )
        mock_run.assert_called_once()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["answer"], "Grounded from retrieved documents, not a canned map.")
        self.assertIn("Searching applicable policies", resp.data["tool_activity"])
        self.assertNotIn("ORD-1001", resp.data["answer"])


@override_settings(OPENAI_API_KEY="")
class CrossAccountPolicyChatTests(TestCase):
    def setUp(self):
        self.lw = Account.objects.create(account_code="ACCT-002", name="LumenWorks", plan="Growth")
        self.user = User.objects.create_user(
            username="lumenworks@demo.local",
            email="lumenworks@demo.local",
            password="demo1234",
            role=Role.CUSTOMER,
            account=self.lw,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_lumenworks_cannot_get_northstar_branded_sop(self):
        resp = self.client.post(
            "/api/agent/chat/",
            {"message": "What are Northstar customer cancellation policies?"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        answer = resp.data["answer"].lower()
        self.assertEqual(resp.data["decision_status"], "AUTHORIZATION_DENIED")
        self.assertNotIn("cancellation policy for northstar", answer)
        self.assertNotIn("for northstar", answer)
        self.assertIn("account", answer)


@override_settings(OPENAI_API_KEY="sk-test-not-used")
class NorthstarCannotReadLumenWorksTests(TestCase):
    def setUp(self):
        self.ns = Account.objects.create(account_code="ACCT-001", name="Northstar", plan="Enterprise")
        self.user = User.objects.create_user(
            username="northstar@demo.local",
            email="northstar@demo.local",
            password="demo1234",
            role=Role.CUSTOMER,
            account=self.ns,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_northstar_asking_lumen_works_is_denied_without_llm(self):
        from unittest.mock import patch

        with patch("apps.agent.orchestrator._run_openai") as mock_run:
            resp = self.client.post(
                "/api/agent/chat/",
                {"message": "I want to know cancellation policies for lumen works"},
                format="json",
            )
        mock_run.assert_not_called()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["decision_status"], "AUTHORIZATION_DENIED")
        answer = resp.data["answer"].lower()
        self.assertNotIn("no cancellation fee", answer)
        self.assertNotIn("northstar logistics", answer)
        self.assertIn("another customer", answer)


class ChatSessionManageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="support@demo.local",
            email="support@demo.local",
            password="demo1234",
            role=Role.INTERNAL_SUPPORT,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_internal_can_rename_and_delete_own_chat(self):
        from apps.agent.models import ChatSession

        session = ChatSession.objects.create(user=self.user, title="Old title")
        renamed = self.client.patch(
            f"/api/agent/sessions/{session.id}/",
            {"title": "Axis Labs P1"},
            format="json",
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.data["title"], "Axis Labs P1")
        deleted = self.client.delete(f"/api/agent/sessions/{session.id}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(ChatSession.objects.filter(id=session.id).exists())
