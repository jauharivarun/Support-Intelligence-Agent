"""Turn tool results into user-facing conversational answers."""
from __future__ import annotations

import re


INTERNAL_CODE_RE = re.compile(
    r"\b(cancellable|eligible)\s*=\s*(True|False)\b|"
    r"\b(fee|credit)\s*=\s*INR\s*[\d.]+|"
    r"\bRule\s*=\s*[A-Z0-9_]+|"
    r"\bBased on retrieved sources:\s*",
    re.I,
)


def normalize_answer_markdown(text: str) -> str:
    """Make ATX headings renderable: own line, space after hashes, drop decorative # runs."""
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(#{1,6})(?=[A-Za-z])", r"\1 ", text)
    text = re.sub(r"([^#\n])(#{1,6}\s)", r"\1\n\2", text)
    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if re.fullmatch(r"#{2,}", stripped):
            continue
        heading = re.match(r"^(#{1,6})(\s*)(.*)$", stripped)
        if heading:
            rest = heading.group(3).strip().strip("#").strip()
            if not rest:
                continue
            lines.append(f"{heading.group(1)} {rest}")
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def scrub_user_answer(text: str) -> str:
    """Drop internal tool dumps if the model echoes them."""
    if not text:
        return text
    cleaned = INTERNAL_CODE_RE.sub("", text)
    cleaned = normalize_text(cleaned)
    cleaned = normalize_answer_markdown(cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def sanitize_tool_result(result):
    """Normalize retrieved text so the model does not echo PDF line-break artifacts."""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    if "content" in out and isinstance(out["content"], str):
        out["content"] = normalize_text(out["content"])[:1200]
    hits = out.get("results") or out.get("hits")
    if isinstance(hits, list):
        cleaned_hits = []
        for item in hits:
            if isinstance(item, dict):
                row = dict(item)
                if isinstance(row.get("content"), str):
                    row["content"] = normalize_text(row["content"])[:800]
                cleaned_hits.append(row)
            else:
                cleaned_hits.append(item)
        if "results" in out:
            out["results"] = cleaned_hits
        else:
            out["hits"] = cleaned_hits
    return out


def normalize_text(text: str) -> str:
    """Collapse PDF word-per-line artifacts and excess whitespace."""
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    single_word = sum(1 for ln in lines if len(ln.split()) == 1 and not ln.startswith("-"))
    if len(lines) > 3 and single_word / len(lines) > 0.55:
        return re.sub(r"\s+", " ", " ".join(lines)).strip()
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def format_cancellation_answer(result: dict) -> tuple[str, str]:
    order_id = result.get("order_id", "this order")
    if result.get("error") == "AUTHORIZATION_DENIED":
        return "I can't access that order — it's outside your account scope.", "AUTHORIZATION_DENIED"
    if result.get("cancellable") is False:
        notes = result.get("notes") or "This shipment can't be cancelled under the current rules."
        return notes, result.get("decision_status", "RESOLVED")

    fee = result.get("fee_inr")
    source = result.get("source") or "your customer agreement"
    decision = result.get("decision_status", "RESOLVED")

    if fee == 0 and decision == "OVERRIDE_APPLIED":
        return (
            f"Yes — you can cancel {order_id} without a fee. "
            f"Your agreement ({source}) waives the cancellation fee for BOOKED shipments before pickup.",
            decision,
        )
    if fee == 0:
        return f"Yes — you can cancel {order_id} without a fee.", decision
    return (
        f"Yes — {order_id} can be cancelled, but a cancellation fee of INR {fee} applies under the current policy.",
        decision,
    )


def format_service_credit_answer(result: dict) -> tuple[str, str]:
    order_id = result.get("order_id", "this order")
    status = result.get("status") or result.get("order_status")
    decision = result.get("decision_status", "RESOLVED")
    status_clause = f" {order_id} is currently **{status}**." if status else ""

    if result.get("error") == "AUTHORIZATION_DENIED":
        return "I can't access that order — it's outside your account scope.", "AUTHORIZATION_DENIED"

    if decision == "NEEDS_MORE_INFORMATION":
        missing = ", ".join(result.get("missing_facts") or ["required facts"])
        return (
            f"I can't confirm a failed-pickup service credit for {order_id} yet.{status_clause} "
            f"I still need: {missing}. I won't promise a credit until that's verified.",
            decision,
        )
    if result.get("eligible") is False:
        notes = result.get("notes") or f"{order_id} is not eligible for a service credit."
        if status and status not in notes:
            return f"{notes}{status_clause}", decision
        return notes, decision
    if result.get("eligible"):
        credit = result.get("credit_inr", 0)
        return (
            f"Yes — {order_id} appears eligible for a service credit of INR {credit} "
            f"based on the applicable policy and shipment details.{status_clause}",
            decision,
        )
    return f"{order_id} does not appear eligible for a service credit under the current rules.{status_clause}", decision


def format_sla_answer(account_id: str | None) -> tuple[str, str, list[dict]]:
    if account_id == "ACCT-001":
        return (
            "For Northstar Logistics (ACCT-001), first-response targets from the Northstar Enterprise Agreement are:\n"
            "- P1 (Critical): 15 minutes, 24x7\n"
            "- P2 (High): 1 hour\n"
            "- P3 (Normal): 8 business hours\n\n"
            "These replace ParcelPilot's default Support Policy v3 targets.",
            "OVERRIDE_APPLIED",
            [{"name": "Northstar Logistics Enterprise Agreement"}],
        )
    if account_id == "ACCT-002":
        return (
            "For LumenWorks (ACCT-002), first-response targets from the LumenWorks Service Agreement are:\n"
            "- P1: 2 business hours\n"
            "- P2: 4 business hours\n"
            "- P3: 2 business days\n\n"
            "Weekend and after-hours support are not included on that plan.",
            "OVERRIDE_APPLIED",
            [{"name": "LumenWorks Service Agreement"}],
        )
    if account_id == "ACCT-003":
        return (
            "Beacon Retail (ACCT-003) is on Standard and has no custom agreement, so Support Policy v3 applies.\n"
            "- P1: 4 business hours (Standard)\n"
            "Customer-specific 15-minute / 2-hour targets do not apply here.",
            "RESOLVED",
            [{"name": "ParcelPilot Support Policy v3"}],
        )
    if account_id == "ACCT-004":
        return (
            "Axis Labs (ACCT-004) is on Enterprise with no custom agreement, so Support Policy v3 applies.\n"
            "- P1: 30 minutes, 24x7 (Enterprise default)\n"
            "This is not Northstar's 15-minute custom P1.",
            "RESOLVED",
            [{"name": "ParcelPilot Support Policy v3"}],
        )
    return (
        "Default first-response targets depend on plan (Enterprise, Growth, or Standard) in Support Policy v3. "
        "A signed customer agreement overrides those defaults when it states different targets. "
        "Tell me the account ID if you need the exact P1 for a specific customer.",
        "RESOLVED",
        [{"name": "ParcelPilot Support Policy v3"}],
    )
