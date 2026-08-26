"""Deterministic Source Resolution Engine.

Sequence: Applicability → Status → Temporal Validity → Authority → Specificity
→ Explicit Override → Conflict Detection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from django.conf import settings
from django.utils.dateparse import parse_datetime


class DecisionStatus:
    RESOLVED = "RESOLVED"
    OVERRIDE_APPLIED = "OVERRIDE_APPLIED"
    NEEDS_MORE_INFORMATION = "NEEDS_MORE_INFORMATION"
    CONFLICT_REQUIRES_VERIFICATION = "CONFLICT_REQUIRES_VERIFICATION"
    HUMAN_JUDGMENT_REQUIRED = "HUMAN_JUDGMENT_REQUIRED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"


@dataclass
class SourceCandidate:
    document_id: int | None
    name: str
    source_type: str
    status: str
    authority_level: int
    scope_type: str
    account_id: str | None
    effective_date: date | None
    expiry_date: date | None
    explicit_override_domains: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    content_snippet: str = ""
    conclusion: str | None = None  # optional structured conclusion key
    chunk_status: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolutionResult:
    status: str
    applicable_sources: list[SourceCandidate]
    excluded_sources: list[dict]
    primary_source: SourceCandidate | None
    overridden_source: SourceCandidate | None
    reasoning: str
    missing_facts: list[str] = field(default_factory=list)
    conflict_summary: str | None = None


def _parse_reference_date(reference: date | datetime | str | None) -> date:
    if reference is None:
        reference = settings.DATASET_REFERENCE_TIME
    if isinstance(reference, datetime):
        return reference.date()
    if isinstance(reference, date):
        return reference
    dt = parse_datetime(str(reference))
    if dt:
        return dt.date()
    return date.fromisoformat(str(reference)[:10])


def is_temporally_valid(src: SourceCandidate, ref: date) -> bool:
    if src.effective_date and src.effective_date > ref:
        return False
    if src.expiry_date and ref > src.expiry_date:
        return False
    return True


def domain_matches(domain: str | None, listed: list[str]) -> bool:
    if not domain or not listed:
        return False
    domain_u = domain.upper()
    return any(domain_u in d.upper() or d.upper() in domain_u for d in listed)


def explicitly_overrides(src: SourceCandidate, domain: str | None) -> bool:
    """Customer-specific docs override general policy only in listed domains.

    An empty explicit_override_domains list means the agreement may override any domain.
    """
    if src.scope_type != "CUSTOMER_SPECIFIC":
        return False
    if not src.explicit_override_domains:
        return True
    if not domain:
        return False
    return domain_matches(domain, src.explicit_override_domains)


def governing_sort_key(src: SourceCandidate, domain: str | None) -> tuple:
    """Applicability already applied. Rank: explicit override → governing authority → specificity.

    A customer agreement that does not list this domain in explicit_override_domains
    must not outrank the general SOP for that domain.
    """
    override = 1 if explicitly_overrides(src, domain) else 0
    if domain and src.scope_type == "CUSTOMER_SPECIFIC" and not override:
        governing_authority = 0
        specific = 0
    else:
        governing_authority = src.authority_level
        specific = 1 if src.scope_type == "CUSTOMER_SPECIFIC" else 0
    return (-override, -governing_authority, -specific, -src.authority_level)


def retrieval_rank_score(
    similarity: float,
    src: SourceCandidate,
    *,
    domain: str | None,
    account_id: str | None,
) -> float:
    """Blend vector similarity with precedence metadata for retrieval ranking."""
    score = float(similarity)
    score += (max(src.authority_level, 0) / 100.0) * 0.12
    if src.status in {"CURRENT", "ACTIVE"}:
        score += 0.04
    if src.status in {"DEPRECATED", "CONTEXT_ONLY"}:
        score -= 0.5
    same_account = bool(account_id and src.account_id == account_id)
    if explicitly_overrides(src, domain) and same_account:
        score += 0.28
    elif same_account:
        score += 0.04
    if domain_matches(domain, src.domains) or domain_matches(domain, src.explicit_override_domains):
        score += 0.06
    return score


def is_applicable(
    src: SourceCandidate,
    *,
    domain: str | None,
    account_id: str | None,
) -> bool:
    if src.status == "DEPRECATED" or src.authority_level <= 0:
        return False
    if src.status == "CONTEXT_ONLY" or src.source_type == "HISTORICAL_CONTEXT":
        return False  # context only — not authoritative for current decisions
    if src.scope_type == "CUSTOMER_SPECIFIC":
        if not account_id or src.account_id != account_id:
            return False
    if domain and src.domains:
        if not domain_matches(domain, src.domains) and not domain_matches(
            domain, src.explicit_override_domains
        ):
            return False
    return True


def resolve_sources(
    candidates: list[SourceCandidate],
    *,
    domain: str | None = None,
    account_id: str | None = None,
    reference_date: date | datetime | str | None = None,
    missing_facts: list[str] | None = None,
    requires_human_judgment: bool = False,
    conclusions: dict[str, str] | None = None,
) -> ResolutionResult:
    """Resolve which sources govern the answer.

    conclusions: optional map of source name/id → conclusion token for conflict detection
    e.g. {"Northstar Agreement": "NO_FEE", "Cancellation SOP": "FEE_250"}
    """
    ref = _parse_reference_date(reference_date)
    missing_facts = missing_facts or []
    excluded: list[dict] = []
    applicable: list[SourceCandidate] = []

    if requires_human_judgment:
        return ResolutionResult(
            status=DecisionStatus.HUMAN_JUDGMENT_REQUIRED,
            applicable_sources=[],
            excluded_sources=[],
            primary_source=None,
            overridden_source=None,
            reasoning="Discretionary / goodwill / unsupported exception requires human judgment.",
            missing_facts=missing_facts,
        )

    if missing_facts:
        return ResolutionResult(
            status=DecisionStatus.NEEDS_MORE_INFORMATION,
            applicable_sources=[],
            excluded_sources=[],
            primary_source=None,
            overridden_source=None,
            reasoning="Required facts are unavailable after retrieval.",
            missing_facts=missing_facts,
        )

    for src in candidates:
        if src.status == "DEPRECATED" or src.authority_level <= 0:
            excluded.append({"name": src.name, "reason": "deprecated_or_zero_authority"})
            continue
        if src.source_type == "HISTORICAL_CONTEXT" or src.status == "CONTEXT_ONLY":
            excluded.append({"name": src.name, "reason": "historical_context_only"})
            continue
        if not is_temporally_valid(src, ref):
            excluded.append({"name": src.name, "reason": "temporally_invalid"})
            continue
        if not is_applicable(src, domain=domain, account_id=account_id):
            excluded.append({"name": src.name, "reason": "not_applicable"})
            continue
        # chunk-level: resolved known issues should not drive new attribution alone
        if (src.chunk_status or "").upper() == "RESOLVED" and domain == "KNOWN_ISSUE":
            excluded.append({"name": src.name, "reason": "resolved_known_issue"})
            continue
        applicable.append(src)

    if not applicable:
        return ResolutionResult(
            status=DecisionStatus.NEEDS_MORE_INFORMATION,
            applicable_sources=[],
            excluded_sources=excluded,
            primary_source=None,
            overridden_source=None,
            reasoning="No applicable authoritative sources after filtering.",
            missing_facts=["applicable_authoritative_source"],
        )

    applicable.sort(key=lambda s: governing_sort_key(s, domain))
    primary = applicable[0]
    overridden = None
    status = DecisionStatus.RESOLVED
    reasoning = f"Using highest-precedence applicable source: {primary.name}."

    # Explicit override: customer agreement overrides general policy in the same domain
    if explicitly_overrides(primary, domain) and primary.authority_level >= 100:
        lower = [
            s
            for s in applicable
            if s.document_id != primary.document_id and s.authority_level < primary.authority_level
        ]
        if lower:
            overridden = lower[0]
            status = DecisionStatus.OVERRIDE_APPLIED
            reasoning = (
                f"{primary.name} explicitly overrides lower-authority source "
                f"{overridden.name} for domain {domain or 'general'}."
            )

    # Conflict detection among same-authority applicable sources with incompatible conclusions
    conclusions = conclusions or {}
    if conclusions:
        # map applicable sources to conclusions
        grouped: dict[str, list[SourceCandidate]] = {}
        for src in applicable:
            key = conclusions.get(src.name) or conclusions.get(str(src.document_id)) or src.conclusion
            if key:
                grouped.setdefault(key, []).append(src)
        if len(grouped) > 1:
            # if override already resolved across authority levels, keep OVERRIDE
            auth_levels = {s.authority_level for sources in grouped.values() for s in sources}
            if len(auth_levels) == 1:
                status = DecisionStatus.CONFLICT_REQUIRES_VERIFICATION
                reasoning = (
                    "Applicable authoritative sources provide incompatible conclusions "
                    "with no precedence rule."
                )
                return ResolutionResult(
                    status=status,
                    applicable_sources=applicable,
                    excluded_sources=excluded,
                    primary_source=None,
                    overridden_source=None,
                    reasoning=reasoning,
                    conflict_summary="; ".join(
                        f"{k}: {[s.name for s in v]}" for k, v in grouped.items()
                    ),
                )

    return ResolutionResult(
        status=status,
        applicable_sources=applicable,
        excluded_sources=excluded,
        primary_source=primary,
        overridden_source=overridden,
        reasoning=reasoning,
    )


def result_to_dict(result: ResolutionResult) -> dict:
    def src_dict(s: SourceCandidate | None):
        if not s:
            return None
        return {
            "document_id": s.document_id,
            "name": s.name,
            "source_type": s.source_type,
            "status": s.status,
            "authority_level": s.authority_level,
            "scope_type": s.scope_type,
            "account_id": s.account_id,
            "snippet": s.content_snippet[:400] if s.content_snippet else "",
        }

    return {
        "status": result.status,
        "reasoning": result.reasoning,
        "missing_facts": result.missing_facts,
        "conflict_summary": result.conflict_summary,
        "primary_source": src_dict(result.primary_source),
        "overridden_source": src_dict(result.overridden_source),
        "applicable_sources": [src_dict(s) for s in result.applicable_sources],
        "excluded_sources": result.excluded_sources,
    }
