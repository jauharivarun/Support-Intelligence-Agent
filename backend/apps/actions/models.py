from django.conf import settings
from django.db import models


class PendingActionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION", "Awaiting Confirmation"
    CONFIRMED = "CONFIRMED", "Confirmed"
    EXECUTED = "EXECUTED", "Executed"
    CANCELLED = "CANCELLED", "Cancelled"
    EXPIRED = "EXPIRED", "Expired"
    FAILED = "FAILED", "Failed"


class PendingAction(models.Model):
    session = models.ForeignKey(
        "agent.ChatSession",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pending_actions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pending_actions"
    )
    action_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=PendingActionStatus.choices,
        default=PendingActionStatus.AWAITING_CONFIRMATION,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class Escalation(models.Model):
    ticket = models.ForeignKey(
        "tickets.Ticket", null=True, blank=True, on_delete=models.SET_NULL
    )
    account = models.ForeignKey(
        "accounts.Account", null=True, blank=True, on_delete=models.SET_NULL
    )
    severity = models.CharField(max_length=16, blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=32, default="OPEN")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)


class FollowUpTask(models.Model):
    account = models.ForeignKey(
        "accounts.Account", null=True, blank=True, on_delete=models.SET_NULL
    )
    ticket = models.ForeignKey(
        "tickets.Ticket", null=True, blank=True, on_delete=models.SET_NULL
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=32, default="OPEN")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
