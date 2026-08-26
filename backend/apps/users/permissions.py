from rest_framework.permissions import BasePermission

from apps.users.models import Role
import re


ACCOUNT_QUERY_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("ACCT-001", (r"\bacct-001\b", r"\bnorthstar\b")),
    ("ACCT-002", (r"\bacct-002\b", r"\blumenworks\b", r"\blumen\s*works?\b", r"\blumen\b")),
    ("ACCT-003", (r"\bacct-003\b", r"\bbeacon\b")),
    ("ACCT-004", (r"\bacct-004\b", r"\baxis\s+labs\b")),
]


def mentioned_account_codes(text: str) -> list[str]:
    blob = text or ""
    found: list[str] = []
    for code, patterns in ACCOUNT_QUERY_HINTS:
        if any(re.search(p, blob, re.I) for p in patterns):
            found.append(code)
    return found


def preferred_mentioned_account(text: str) -> str | None:
    """Account named latest in the text (so a follow-up customer beats an earlier one)."""
    blob = text or ""
    last_pos = -1
    last_code = None
    for code, patterns in ACCOUNT_QUERY_HINTS:
        for pattern in patterns:
            for match in re.finditer(pattern, blob, re.I):
                if match.start() >= last_pos:
                    last_pos = match.start()
                    last_code = code
    return last_code


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == Role.ADMIN
        )


class IsInternalOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in {Role.INTERNAL_SUPPORT, Role.ADMIN}
        )


# Back-compat aliases used by some views
IsAdminRole = IsAdminRole
IsInternalOrAdmin = IsInternalOrAdmin


def user_context(user) -> dict:
    return {
        "user_id": user.id,
        "role": user.role,
        "account_id": user.account.account_code if user.account_id else None,
        "allowed_account_ids": user.allowed_account_ids(),
        "email": user.email,
        "name": user.name or user.get_full_name() or user.email,
    }


def out_of_scope_account_codes(ctx: dict, *texts: str) -> list[str]:
    """Account codes named in text that this user is not allowed to access."""
    allowed = ctx.get("allowed_account_ids")
    if allowed is None:
        return []
    blob = " ".join(t for t in texts if t)
    return [code for code in mentioned_account_codes(blob) if code not in allowed]


def assert_account_access(ctx: dict, account_code: str | None) -> None:
    if account_code is None:
        return
    allowed = ctx.get("allowed_account_ids")
    if allowed is None:
        return
    if account_code not in allowed:
        raise PermissionError(
            f"AUTHORIZATION_DENIED: account {account_code} is outside allowed scope"
        )
