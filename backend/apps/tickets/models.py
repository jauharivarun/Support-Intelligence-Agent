from django.db import models


class Ticket(models.Model):
    ticket_id = models.CharField(max_length=64, unique=True, db_index=True)
    account = models.ForeignKey(
        "accounts.Account", on_delete=models.CASCADE, related_name="tickets"
    )
    created_at = models.DateTimeField()
    status = models.CharField(max_length=32, db_index=True)
    subject = models.CharField(max_length=512)
    description = models.TextField(blank=True)
    channel = models.CharField(max_length=64, blank=True)
    assigned_to = models.CharField(max_length=128, blank=True)
    last_customer_message_at = models.DateTimeField(null=True, blank=True)
    historical_resolution = models.TextField(blank=True)
    severity = models.CharField(max_length=8, blank=True)
    category = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account", "status"]),
            models.Index(fields=["severity"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self):
        return self.ticket_id
