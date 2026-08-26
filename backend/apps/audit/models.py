from django.conf import settings
from django.db import models


class ActionAuditLog(models.Model):
    pending_action = models.ForeignKey(
        "actions.PendingAction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    action_type = models.CharField(max_length=64)
    request_payload = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    status = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
