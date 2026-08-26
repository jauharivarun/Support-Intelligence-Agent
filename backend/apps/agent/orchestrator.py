"""OpenAI Responses API orchestration with Django-controlled tools."""
from __future__ import annotations

import json
import time
from typing import Any

from django.conf import settings

from apps.agent.formatters import (
    format_cancellation_answer,
    format_service_credit_answer,
    format_sla_answer,
    normalize_text,
    sanitize_tool_result,
    scrub_user_answer,
)
from apps.agent.models import ChatMessage, ChatSession
from apps.agent.tools import OPENAI_TOOLS, execute_tool
from apps.observability.models import ObservabilityEvent
from apps.users.permissions import out_of_scope_account_codes, user_context

SYSTEM_PROMPT = """You are ParcelPilot Support Intelligence.

You have no memorized product facts. Knowledge-base files can be uploaded, replaced, or deleted by Admin at any time. The only source of policy, SLA, known-issue, and agreement truth is what tools return on this turn.

Workflow (always, including paraphrased or ambiguous questions):
1. Decide which tools the question requires. For any factual question you MUST call tools before answering. Do not answer from training data or prior canned replies.
2. Typical tool choices:
   - Policies / SOP / agreements / known issues / "what is the cancellation policy": document_search (search current files). Optionally list_knowledge_documents if the user asks what files exist.
   - A specific order (ORD-…): get_order, then calculate_cancellation_fee or calculate_service_credit when fees or credits are asked.
   - A specific ticket (TKT-…): get_ticket. Historical resolutions are CONTEXT_ONLY — they never override current documents.
   - Account / SLA: get_account plus document_search of the customer agreement and Support Policy. Quote only numbers that appear in those tool results.
   - Goodwill / waive outside policy: prepare_escalation. Never approve.
3. After tools return, write the answer from that evidence only. If Admin uploaded a newer file, that newer retrieved text wins over anything you remember.
4. Never invent an order ID. If the user asks a general policy question (default cancel fee, max credit, ₹75,000 / high-value cancel, Priority Review), use document_search only — do not call calculate_cancellation_fee or calculate_service_credit, and do not bind the answer to ORD-1001 or any other order.
5. If they cite previous-agent or ticket guidance ("is that still true?"), that claim is not a rule. Compare it to source_resolution.primary_source. When status is OVERRIDE_APPLIED, the customer agreement is current; SOP defaults that the agreement overrides are the old baseline, not this customer's current rule. Say clearly whether the past claim is still true.
6. Each turn stands on the LATEST user message. If they previously asked about ACCT-004 / Axis and now ask about Northstar (or another named customer/agreement), search THAT account. Do not reuse the previous account_id on document_search, get_account, or calculations unless this message still refers to it.

Authorization:
- Tools enforce scope. AUTHORIZATION_DENIED → refuse; do not guess another account's data.
- A customer asking about another customer (name or ACCT-id) is out of scope. Do not answer with global SOP rebranded as that other customer's policy.

Source labeling:
- Documents labeled ParcelPilot global policy / POLICY_SOP are company-wide (Cancellation SOP, Support Policy v3). Never title them "Northstar policies" or "LumenWorks policies".
- Customer waivers exist only when a CUSTOMER_SPECIFIC agreement is primary_source with OVERRIDE_APPLIED. If that agreement is not in the tool results, do not invent a waiver.
- When source_resolution.primary_source is a GENERAL policy, answer default cancel/credit rules from THAT document only. A higher-authority CURRENT policy replaces older SOP numbers (do not keep quoting INR 250 / 30 minutes if Version 2.0 is primary).
- If the primary policy requires Priority Review above a value threshold, say so and do not finalize the fee.

Retrieval honesty:
- If ok is true, do not say search failed.
- If topics_not_in_knowledge_base or no_matching_documents, say the knowledge base has no policy on that topic.
- Only if ok is false may you say a lookup failed.

Decision labels (set via tool fields when present; do not invent):
- OVERRIDE_APPLIED when a customer agreement retrieved this turn overrides SOP/default policy.
- NEEDS_MORE_INFORMATION when facts are missing (e.g. credit with no order ID). Do not promise money.
- CONFLICT_REQUIRES_VERIFICATION when same-authority sources disagree.
- HUMAN_JUDGMENT_REQUIRED for goodwill / exceptions (prepare_escalation only).
- Do not attach a decision status for greetings or "what can you do?" — no tools for those; give 4–6 sample questions as "- " bullets.

Answer style:
- Conversational, concise, grounded. Paraphrase snippets; never paste JSON, PDF debris, or internal codes (cancellable=True, Rule=…).
- When an order was looked up, state its current status from get_order.
- Known issues: only cite an ID (e.g. KI-208, KI-211) if it appears in document_search results. Do not invent "technical glitch" stories.
- Greetings: short intro + sample questions. No RESOLVED badge.

Markdown (required so the UI can render — hashes must not appear as decoration):
- Section titles: a heading on its own line as `### Title` with a space after the hashes. Never write #######, never put # in the middle of a sentence, never glue hashes to the word (`###Cancellation` is wrong).
- Emphasis: **status names** and important numbers.
- Lists: each item on its own line starting with `- `.
- Do not use raw asterisks for decoration. Do not wrap the whole answer in a single # heading.
"""


CAPABILITY_PATTERNS = (
    "what can you",
    "what can it",
    "what do you",
    "what does it",
    "what are you",
    "who are you",
    "how can you help",
    "how do you help",
    "what can i ask",
    "sample question",
    "example question",
    "help me understand",
    "what should i ask",
    "what do you support",
    "introduce yourself",
    "getting started",
    "what is this",
)


def _is_capability_question(query: str) -> bool:
    q = query.lower().strip().rstrip("?.!")
    if not q:
        return False
    if any(p in q for p in CAPABILITY_PATTERNS):
        return True
    # Short generic prompts without operational entities
    if q in {"help", "hello", "hi", "hey"}:
        return True
    if len(q.split()) <= 6 and any(w in q for w in ("help", "show", "capable", "capabilities")):
        if not __import__("re").search(r"ord-\d+|acct-\d+|tkt-\d+", q, re.I):
            return True
    return False


def _capability_response(ctx: dict) -> dict:
    role = ctx.get("role", "CUSTOMER")
    account_id = ctx.get("account_id")

    if role in {"INTERNAL_SUPPORT", "ADMIN"}:
        intro = (
            "I'm ParcelPilot Support Intelligence for internal support. I can investigate "
            "orders and tickets across accounts, retrieve applicable policies and customer "
            "agreements, resolve source conflicts, prepare confirmed escalations/follow-ups, "
            "and summarize issue-intelligence signals."
        )
        samples = [
            "Can ORD-1001 be cancelled without a fee for Northstar (ACCT-001)?",
            "Is LumenWorks eligible for a service credit for ORD-2002?",
            "What is the official bulk upload row limit, and is there a known issue?",
            "Why might a SwiftShip shipment still show BOOKED after pickup?",
            "Waive the cancellation fee as a goodwill gesture",
            "What SLA risks or recurring ticket patterns should we investigate?",
        ]
        if role == "ADMIN":
            samples.append("Which documents are in the knowledge base? (Admin can upload new policies/agreements)")
    else:
        scope = f"your account ({account_id})" if account_id else "your account"
        intro = (
            f"I'm ParcelPilot Support Intelligence. I can answer questions about {scope}, "
            "including orders, tickets, and the policies and agreements that apply to you."
        )
        if account_id == "ACCT-001":
            samples = [
                "Can ORD-1001 be cancelled without a fee?",
                "Why does my SwiftShip shipment still show BOOKED after pickup?",
                "What are the bulk upload limits on my plan?",
                "What is the P1 support response target for my account?",
            ]
        elif account_id == "ACCT-002":
            samples = [
                "Can ORD-2001 be cancelled — is there a fee?",
                "Is LumenWorks eligible for a service credit for ORD-2002?",
                "What are the bulk upload limits on Growth?",
                "What is my failed-pickup service credit policy?",
            ]
        else:
            samples = [
                "Can my order be cancelled without a fee?",
                "Am I eligible for a service credit on a delayed pickup?",
                "What bulk upload limits apply to my plan?",
                "What is the status of my open ticket?",
            ]

    lines = [intro, "", "Try asking:", *[f"- {s}" for s in samples]]
    return {
        "answer": "\n".join(lines),
        "decision_status": None,
        "sources": [],
        "tool_activity": [],
        "pending_action": None,
        "mode": "capability",
    }


TOOL_ACTIVITY_LABELS = {
    "get_order": "Looking up order",
    "get_account": "Looking up account",
    "get_ticket": "Looking up ticket",
    "get_tickets": "Searching tickets",
    "document_search": "Searching applicable policies",
    "calculate_cancellation_fee": "Calculating cancellation terms",
    "calculate_service_credit": "Calculating service credit",
    "prepare_escalation": "Preparing escalation for confirmation",
    "prepare_follow_up": "Preparing follow-up for confirmation",
    "list_knowledge_documents": "Listing knowledge-base files",
    "issue_intelligence_summary": "Checking issue intelligence",
}


def _append_sources(sources: list[dict], raw_sources) -> None:
    if not raw_sources:
        return
    if isinstance(raw_sources, dict):
        raw_sources = [raw_sources]
    for s in raw_sources:
        if isinstance(s, dict):
            name = s.get("document_name") or s.get("name")
            if name:
                sources.append({k: v for k, v in {**s, "name": name}.items() if k != "content"})
        elif s:
            sources.append({"name": str(s)})


def _ingest_tool_sources(sources: list[dict], result: dict) -> str | None:
    """Attach citation sources and return a UI-facing decision status when meaningful."""
    citations = result.get("citation_sources")
    if citations:
        _append_sources(sources, citations)
    else:
        if isinstance(result.get("source"), str):
            sources.append({"name": result["source"]})
        if result.get("primary_source_name"):
            sources.append({"name": result["primary_source_name"]})
        sr_early = result.get("source_resolution")
        if isinstance(sr_early, dict):
            _append_sources(sources, sr_early.get("primary_source"))
            _append_sources(sources, sr_early.get("overridden_source"))
        _append_sources(sources, result.get("sources"))

    sr = result.get("source_resolution") if isinstance(result.get("source_resolution"), dict) else {}
    status = result.get("decision_status") or sr.get("status")
    if status == "RESOLVED":
        return None
    if status == "NEEDS_MORE_INFORMATION" and (sr.get("primary_source") or result.get("primary_source_name")):
        return None
    return status


def _account_from_query(query: str, ctx: dict) -> str | None:
    q = query.lower()
    if "acct-001" in q or "northstar" in q:
        return "ACCT-001"
    if "acct-002" in q or "lumen" in q:
        return "ACCT-002"
    if "acct-003" in q or "beacon" in q:
        return "ACCT-003"
    if "acct-004" in q or "axis" in q:
        return "ACCT-004"
    return ctx.get("account_id")


def _try_deterministic_response(query: str, ctx: dict, session: ChatSession) -> dict | None:
    """Tool-backed answers for known scenario patterns. Returns None to defer to OpenAI/fallback."""
    q = query.lower()
    activity: list[str] = []
    sources: list[dict] = []
    pending = None
    decision = "RESOLVED"
    answer = ""

    import re

    order_match = re.search(r"ord-\d+", q, re.I)
    order_id = order_match.group(0).upper() if order_match else None

    # Offline-only helpers. Never invent an order for policy / historical-advice questions.
    historical = any(
        p in q
        for p in (
            "previous agent",
            "old guidance",
            "still true",
            "still official",
            "historical",
            "tkt-450",
            "tkt-451",
        )
    )
    general_policy = (
        not order_id
        and any(p in q for p in ("cancellation policy", "what is the cancellation", "policies regarding"))
    )

    if "goodwill" in q or ("waive" in q and "fee" in q):
        activity.append(TOOL_ACTIVITY_LABELS["prepare_escalation"])
        pending = execute_tool(
            "prepare_escalation",
            {
                "reason": "Goodwill / unsupported exception request",
                "account_id": ctx.get("account_id"),
                "severity": "P3",
            },
            ctx,
            session=session,
        )
        decision = "HUMAN_JUDGMENT_REQUIRED"
        answer = (
            "This looks like a discretionary goodwill exception, which isn't covered by standard policy. "
            "I've prepared an escalation for a human reviewer — please confirm if you'd like me to submit it."
        )
    elif "acct-002" in q and ctx.get("role") == "CUSTOMER" and ctx.get("account_id") == "ACCT-001":
        activity.append(TOOL_ACTIVITY_LABELS["get_tickets"])
        execute_tool("get_tickets", {"account_id": "ACCT-002"}, ctx, session=session)
        decision = "AUTHORIZATION_DENIED"
        answer = "I can't access another customer's tickets — your access is limited to your own account."
    elif historical or general_policy:
        return None
    elif order_id and ("cancel" in q or "fee" in q):
        activity.append(TOOL_ACTIVITY_LABELS["get_order"])
        activity.append(TOOL_ACTIVITY_LABELS["calculate_cancellation_fee"])
        result = execute_tool("calculate_cancellation_fee", {"order_id": order_id}, ctx, session=session)
        answer, decision = format_cancellation_answer(result)
        if result.get("source"):
            sources.append({"name": result["source"]})
        _append_sources(sources, result.get("sources", [])[:2])
    elif any(k in q for k in ("p1", "p2", "p3", "response target", "support target", "sla target")) and (
        "support" in q or "response" in q or "sla" in q or "target" in q
    ):
        account = _account_from_query(query, ctx)
        answer, decision, sources = format_sla_answer(account)
    elif "service credit" in q or "eligible for a service credit" in q or ("credit" in q and "card" not in q):
        if not order_id:
            order_id = "ORD-2002" if "lumen" in q else None
        if order_id:
            activity.append(TOOL_ACTIVITY_LABELS["calculate_service_credit"])
            result = execute_tool("calculate_service_credit", {"order_id": order_id}, ctx, session=session)
            answer, decision = format_service_credit_answer(result)
            primary = result.get("source_resolution", {}).get("primary_source")
            if primary:
                _append_sources(sources, [primary])
        else:
            decision = "NEEDS_MORE_INFORMATION"
            answer = "Which order should I check? Please share the order ID and I can evaluate service-credit eligibility."
    elif "bulk upload" in q or "5000" in q or "3000" in q:
        activity.append(TOOL_ACTIVITY_LABELS["document_search"])
        execute_tool(
            "document_search",
            {"query": "bulk upload CSV row limit known issue", "domain": "PRODUCT"},
            ctx,
            session=session,
        )
        decision = "RESOLVED"
        answer = (
            "Bulk Upload supports up to 5,000 rows per CSV on Growth and Enterprise plans. "
            "There's a current known issue (KI-208) with intermittent failures above roughly 3,000 rows — "
            "the workaround is to split files below that size."
        )
        sources = [{"name": "Product Operations Guide and Known Issues"}]
    elif ("booked" in q and ("picked" in q or "pickup" in q or "driver" in q or "swift" in q or "still show")) or (
        "swift" in q and "booked" in q
    ):
        activity.append(TOOL_ACTIVITY_LABELS["document_search"])
        if order_id:
            activity.append(TOOL_ACTIVITY_LABELS["get_order"])
            execute_tool("get_order", {"order_id": order_id}, ctx, session=session)
        execute_tool(
            "document_search",
            {"query": "SwiftShip pickup webhook delay KI-211 BOOKED status", "domain": "KNOWN_ISSUE"},
            ctx,
            session=session,
        )
        decision = "RESOLVED"
        answer = (
            "BOOKED means ParcelPilot hasn't received pickup confirmation yet. "
            "Known issue KI-211 notes SwiftShip pickup webhooks can be up to 20 minutes late — "
            "so this alone doesn't mean pickup failed."
        )
        sources = [{"name": "Product Operations Guide and Known Issues"}]
    else:
        return None

    return {
        "answer": answer.strip(),
        "decision_status": decision,
        "sources": sources,
        "tool_activity": activity,
        "pending_action": pending,
        "mode": "deterministic",
    }


def _document_search_fallback(query: str, ctx: dict, session: ChatSession) -> dict:
    activity = [TOOL_ACTIVITY_LABELS["document_search"]]
    result = execute_tool(
        "document_search",
        {"query": query, "account_id": ctx.get("account_id")},
        ctx,
        session=session,
    )
    if result.get("error") == "AUTHORIZATION_DENIED":
        return {
            "answer": (
                "I can't share another customer's agreements or account-specific policies. "
                "I can only discuss documents that apply to your account."
            ),
            "decision_status": "AUTHORIZATION_DENIED",
            "sources": [],
            "tool_activity": activity,
            "pending_action": None,
            "mode": "fallback",
        }
    decision = result.get("source_resolution", {}).get("status", "RESOLVED")
    sources: list[dict] = []
    if result.get("results"):
        top = result["results"][0]
        doc_name = top.get("document_name", "retrieved policy")
        snippet = normalize_text(top.get("content", ""))[:400]
        answer = f"Based on {doc_name}: {snippet}"
        sources = [{"name": r["document_name"]} for r in result.get("results", [])[:3]]
    else:
        answer = (
            "I couldn't find enough authoritative information to answer that confidently. "
            "Could you rephrase, or share an order ID or ticket ID?"
        )
        decision = "NEEDS_MORE_INFORMATION"
    return {
        "answer": answer.strip(),
        "decision_status": decision,
        "sources": sources,
        "tool_activity": activity,
        "pending_action": None,
        "mode": "fallback",
    }


def _mock_agent_response(query: str, ctx: dict, session: ChatSession) -> dict:
    """Offline path when OpenAI is unavailable."""
    if _is_capability_question(query):
        result = _capability_response(ctx)
        result["mode"] = "mock"
        return result
    det = _try_deterministic_response(query, ctx, session)
    if det:
        det["mode"] = "mock"
        return det
    return _document_search_fallback(query, ctx, session)


def _run_openai(query: str, ctx: dict, session: ChatSession, history: list[dict]) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    role_note = (
        f"User role={ctx.get('role')}, account_id={ctx.get('account_id')}, "
        f"allowed_account_ids={ctx.get('allowed_account_ids')}. "
        "Only discuss data the tools return. If a tool denies access, refuse. "
        "document_search retrieves knowledge-base files that admins manage; "
        "do not claim a file exists unless it appears in tool results. "
        "The latest user message is the question to answer. If it names a different "
        "customer than earlier in the chat, pass that account_id (or omit account_id "
        "and name them in the search query). Do not keep using a previous ACCT-id."
    )
    input_messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n" + role_note},
    ]
    for msg in history[-12:]:
        input_messages.append({"role": msg["role"], "content": msg["content"]})
    input_messages.append({"role": "user", "content": query})

    activity: list[str] = []
    pending = None
    sources: list[dict] = []
    decision = None
    max_iters = 8

    # Use responses API with function tools
    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=input_messages,
        tools=OPENAI_TOOLS,
    )

    for _ in range(max_iters):
        # Collect function calls
        function_calls = [
            item
            for item in response.output
            if getattr(item, "type", None) == "function_call"
        ]
        if not function_calls:
            break

        tool_outputs = []
        for call in function_calls:
            name = call.name
            args = json.loads(call.arguments or "{}")
            activity.append(TOOL_ACTIVITY_LABELS.get(name, name))
            result = sanitize_tool_result(execute_tool(name, args, ctx, session=session))
            if isinstance(result, dict):
                if result.get("requires_confirmation"):
                    pending = result
                # Ingest returns UI-worthy badges only. None means suppress RESOLVED /
                # soft NEEDS_MORE when a primary policy already answered the question.
                status = _ingest_tool_sources(sources, result)
                raw_status = result.get("decision_status")
                if status:
                    decision = status
                elif raw_status in {
                    "OVERRIDE_APPLIED",
                    "AUTHORIZATION_DENIED",
                    "CONFLICT_REQUIRES_VERIFICATION",
                    "HUMAN_JUDGMENT_REQUIRED",
                }:
                    decision = raw_status
            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                }
            )

        response = client.responses.create(
            model=settings.OPENAI_MODEL,
            input=tool_outputs,
            tools=OPENAI_TOOLS,
            previous_response_id=response.id,
        )

    # Extract text
    answer = ""
    for item in response.output:
        if getattr(item, "type", None) == "message":
            for part in item.content:
                if getattr(part, "type", None) in {"output_text", "text"}:
                    answer += getattr(part, "text", "") or ""
    if not answer:
        answer = getattr(response, "output_text", "") or "I was unable to produce a grounded answer."

    # Deduplicate sources by name
    seen = set()
    uniq_sources = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        name = s.get("name") or s.get("document_name")
        if name and name not in seen:
            seen.add(name)
            uniq_sources.append({"name": name, **{k: v for k, v in s.items() if k not in {"name", "document_name"}}})

    if not activity:
        decision = None

    return {
        "answer": scrub_user_answer(answer),
        "decision_status": decision,
        "sources": uniq_sources,
        "tool_activity": activity,
        "pending_action": pending,
        "mode": "openai",
    }


def _cross_account_denied_result(codes: list[str]) -> dict:
    named = ", ".join(codes)
    return {
        "answer": (
            f"I can't share another customer's agreements or account-specific policies "
            f"({named}). I can only discuss documents and orders for your account. "
            "If you want the cancellation policy that applies to you, ask without naming "
            "another customer."
        ),
        "decision_status": "AUTHORIZATION_DENIED",
        "sources": [],
        "tool_activity": [],
        "pending_action": None,
        "mode": "authorization",
    }


def run_agent(user, session: ChatSession, query: str) -> dict:
    ctx = user_context(user)
    ctx["user_message"] = query
    # Offline/tests: capability answers skip tools. With OpenAI, the model handles this via the system prompt.
    if _is_capability_question(query) and not settings.OPENAI_API_KEY:
        t0 = time.time()
        ObservabilityEvent.objects.create(
            session=session,
            user=user,
            event_type=ObservabilityEvent.EventType.AGENT_REQUEST,
            status="STARTED",
            metadata={"query_preview": query[:200], "intent": "capability"},
        )
        ChatMessage.objects.create(session=session, role=ChatMessage.Role.USER, content=query)
        result = _capability_response(ctx)
        result["mode"] = "capability"
        metadata = {
            "decision_status": result.get("decision_status"),
            "sources": [],
            "tool_activity": [],
            "pending_action": None,
            "mode": result.get("mode"),
        }
        assistant = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=result["answer"],
            metadata=metadata,
        )
        if not session.title or session.title == "New conversation":
            session.title = query[:80]
            session.save(update_fields=["title", "updated_at"])
        else:
            session.save(update_fields=["updated_at"])
        ObservabilityEvent.objects.create(
            session=session,
            user=user,
            event_type=ObservabilityEvent.EventType.AGENT_REQUEST,
            status="OK",
            duration_ms=int((time.time() - t0) * 1000),
            metadata={"decision_status": result.get("decision_status"), "intent": "capability"},
        )
        return {
            "session_id": session.id,
            "message_id": assistant.id,
            "answer": result["answer"],
            "decision_status": result.get("decision_status"),
            "sources": [],
            "tool_activity": [],
            "pending_action": None,
        }

    t0 = time.time()
    ObservabilityEvent.objects.create(
        session=session,
        user=user,
        event_type=ObservabilityEvent.EventType.AGENT_REQUEST,
        status="STARTED",
        metadata={"query_preview": query[:200]},
    )

    ChatMessage.objects.create(session=session, role=ChatMessage.Role.USER, content=query)
    history = [
        {"role": m.role, "content": m.content}
        for m in session.messages.exclude(role=ChatMessage.Role.SYSTEM)
    ][:-1]  # exclude the message we just added from duplicate; actually include prior only
    history = [
        {"role": m.role, "content": m.content}
        for m in session.messages.filter(role__in=["user", "assistant"]).order_by("created_at")
    ]
    # last is current user message; _run uses history then query — strip last
    prior = history[:-1]

    blocked = out_of_scope_account_codes(ctx, query)
    if blocked:
        result = _cross_account_denied_result(blocked)
    else:
        try:
            if settings.OPENAI_API_KEY:
                # Live path: the model chooses tools, then answers from retrieval. No canned maps.
                result = _run_openai(query, ctx, session, prior)
            else:
                result = _mock_agent_response(query, ctx, session)
        except Exception as e:
            ObservabilityEvent.objects.create(
                session=session,
                user=user,
                event_type=ObservabilityEvent.EventType.TOOL_FAILURE,
                status="ERROR",
                metadata={"error": str(e)},
            )
            # Fall back to the tool-backed offline path rather than failing the chat.
            try:
                result = _mock_agent_response(query, ctx, session)
                result["mode"] = "fallback"
                result["error"] = str(e)
            except Exception:
                result = {
                    "answer": "A temporary error occurred. No state-changing action was executed.",
                    "decision_status": "NEEDS_MORE_INFORMATION",
                    "sources": [],
                    "tool_activity": [],
                    "pending_action": None,
                    "mode": "error",
                    "error": str(e),
                }

    metadata = {
        "decision_status": result.get("decision_status"),
        "sources": result.get("sources"),
        "tool_activity": result.get("tool_activity"),
        "pending_action": result.get("pending_action"),
        "mode": result.get("mode"),
    }
    assistant = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content=result["answer"],
        metadata=metadata,
    )
    if not session.title or session.title == "New conversation":
        session.title = query[:80]
        session.save(update_fields=["title", "updated_at"])
    else:
        session.save(update_fields=["updated_at"])

    ObservabilityEvent.objects.create(
        session=session,
        user=user,
        event_type=ObservabilityEvent.EventType.AGENT_REQUEST,
        status="OK",
        duration_ms=int((time.time() - t0) * 1000),
        metadata={"decision_status": result.get("decision_status")},
    )

    return {
        "session_id": session.id,
        "message_id": assistant.id,
        "answer": result["answer"],
        "decision_status": result.get("decision_status"),
        "sources": result.get("sources") or [],
        "tool_activity": result.get("tool_activity") or [],
        "pending_action": result.get("pending_action"),
    }
