from django.conf import settings
from django.db import models


class ObservabilityEvent(models.Model):
    class EventType(models.TextChoices):
        AGENT_REQUEST = "AGENT_REQUEST", "Agent Request"
        TOOL_CALL = "TOOL_CALL", "Tool Call"
        TOOL_SUCCESS = "TOOL_SUCCESS", "Tool Success"
        TOOL_FAILURE = "TOOL_FAILURE", "Tool Failure"
        SOURCE_CONFLICT = "SOURCE_CONFLICT", "Source Conflict"
        AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED", "Authorization Denied"
        PENDING_ACTION_CREATED = "PENDING_ACTION_CREATED", "Pending Action Created"
        ACTION_CONFIRMED = "ACTION_CONFIRMED", "Action Confirmed"
        ACTION_EXECUTED = "ACTION_EXECUTED", "Action Executed"
        ACTION_FAILED = "ACTION_FAILED", "Action Failed"

    session = models.ForeignKey(
        "agent.ChatSession",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    event_type = models.CharField(max_length=64, choices=EventType.choices)
    tool_name = models.CharField(max_length=128, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=32, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
