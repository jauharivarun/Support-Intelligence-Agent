from django.db import models


class Order(models.Model):
    order_id = models.CharField(max_length=64, unique=True, db_index=True)
    account = models.ForeignKey(
        "accounts.Account", on_delete=models.CASCADE, related_name="orders"
    )
    carrier = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=64, db_index=True)
    booked_at = models.DateTimeField(null=True, blank=True)
    pickup_window_start = models.DateTimeField(null=True, blank=True)
    pickup_window_end = models.DateTimeField(null=True, blank=True)
    pickup_actual_at = models.DateTimeField(null=True, blank=True)
    shipment_fee_inr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    carrier_fault = models.BooleanField(default=False)
    customer_fault = models.BooleanField(default=False)
    cancellation_requested_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order_id"]
        indexes = [
            models.Index(fields=["account", "status"]),
            models.Index(fields=["carrier"]),
        ]

    def __str__(self):
        return self.order_id
