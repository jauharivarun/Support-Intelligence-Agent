from django.db import models


class Account(models.Model):
    account_code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    plan = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, default="active")
    csm = models.CharField(max_length=255, blank=True)
    contract_file = models.CharField(max_length=255, blank=True)
    premium_support = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["account_code"]

    def __str__(self):
        return f"{self.account_code} — {self.name}"
