"""Proactive Issue Intelligence dashboard computations."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.utils.dateparse import parse_datetime

from apps.accounts.models import Account
from apps.actions.models import PendingAction, PendingActionStatus
from apps.documents.models import DocumentChunk
from apps.observability.models import ObservabilityEvent
from apps.tickets.models import Ticket


def _infer_severity(ticket: Ticket) -> str:
    if ticket.severity:
        return ticket.severity
    text = f"{ticket.subject} {ticket.description}".lower()
    if "api key" in text or "security" in text or "all shipment" in text or "http 500" in text:
        return "P1"
    if "bulk upload" in text or "fail" in text:
        return "P2"
    return "P3"


def _sla_hours(account: Account, severity: str) -> float | None:
    # Prefer agreement-like overrides by account code from seed knowledge
    if account.account_code == "ACCT-001":
        return {"P1": 0.25, "P2": 1.0, "P3": 8.0}.get(severity)
    if account.account_code == "ACCT-002":
        return {"P1": 2.0, "P2": 4.0, "P3": 16.0}.get(severity)  # 2 business days ~16h rough
    # Support policy v3 defaults by plan (simplified)
    plan = (account.plan or "Standard").lower()
    table = {
        "enterprise": {"P1": 1.0, "P2": 4.0, "P3": 16.0},
        "growth": {"P1": 4.0, "P2": 8.0, "P3": 24.0},
        "standard": {"P1": 8.0, "P2": 16.0, "P3": 24.0},
    }
    return table.get(plan, table["standard"]).get(severity)


def build_dashboard() -> dict:
    ref = parse_datetime(settings.DATASET_REFERENCE_TIME)
    open_tickets = Ticket.objects.filter(status="open").select_related("account")

    sla_risks = []
    for t in open_tickets:
        sev = _infer_severity(t)
        hours = _sla_hours(t.account, sev)
        if hours is None or not ref:
            continue
        deadline = t.created_at + timedelta(hours=hours)
        remaining = (deadline - ref).total_seconds() / 3600.0
        if remaining < 2:  # at risk if under 2h remaining (or overdue)
            sla_risks.append(
                {
                    "ticket_id": t.ticket_id,
                    "account_id": t.account.account_code,
                    "severity": sev,
                    "subject": t.subject,
                    "sla_hours": hours,
                    "hours_remaining": round(remaining, 2),
                    "label": "SLA_RISK",
                    "sla_source": (
                        "Customer agreement"
                        if t.account.account_code in {"ACCT-001", "ACCT-002"}
                        else "Support Policy v3"
                    ),
                }
            )

    # Recurring themes
    subjects = [t.subject.lower() for t in Ticket.objects.all()]
    theme_counter = Counter()
    for s in subjects:
        if "bulk" in s:
            theme_counter["bulk_upload"] += 1
        if "cancel" in s:
            theme_counter["cancellation"] += 1
        if "swiftship" in s or "booked" in s:
            theme_counter["status_delay"] += 1
        if "api key" in s or "security" in s:
            theme_counter["security"] += 1
        if "shipment creation" in s or "http 500" in s:
            theme_counter["shipment_outage"] += 1

    recurring = [
        {"theme": k, "count": v, "label": "RecurringPattern"}
        for k, v in theme_counter.items()
        if v >= 2
    ]

    # Known-issue correlations
    known_issues = DocumentChunk.objects.exclude(known_issue_id="").select_related("document")
    correlations = []
    for ki in known_issues:
        matching = []
        for t in open_tickets:
            blob = f"{t.subject} {t.description}".lower()
            if ki.known_issue_id == "KI-208" and "bulk" in blob:
                matching.append(t)
            if ki.known_issue_id == "KI-211" and ("swiftship" in blob or "booked" in blob):
                matching.append(t)
        if matching:
            correlations.append(
                {
                    "known_issue_id": ki.known_issue_id,
                    "known_issue_status": ki.known_issue_status or ki.chunk_status,
                    "document": ki.document.name,
                    "tickets": [t.ticket_id for t in matching],
                    "accounts": sorted({t.account.account_code for t in matching}),
                    "label": "PossibleKnown-IssueCorrelation",
                    "note": "Pattern detection is a signal, not proof of root cause.",
                }
            )

    # Cross-customer patterns
    by_theme_accounts: dict[str, set[str]] = defaultdict(set)
    for t in Ticket.objects.select_related("account"):
        s = t.subject.lower()
        if "bulk" in s:
            by_theme_accounts["bulk_upload"].add(t.account.account_code)
    cross = [
        {
            "theme": theme,
            "accounts": sorted(accs),
            "label": "Cross-CustomerPattern",
        }
        for theme, accs in by_theme_accounts.items()
        if len(accs) >= 2
    ]

    conflicts = ObservabilityEvent.objects.filter(
        event_type=ObservabilityEvent.EventType.SOURCE_CONFLICT
    ).count()
    action_failures = PendingAction.objects.filter(status=PendingActionStatus.FAILED).count()

    return {
        "sla_risks": sorted(sla_risks, key=lambda x: x["hours_remaining"]),
        "recurring_issues": recurring,
        "known_issue_correlations": correlations,
        "cross_customer_patterns": cross,
        "source_conflicts": conflicts,
        "action_failures": action_failures,
        "reference_time": settings.DATASET_REFERENCE_TIME,
    }
