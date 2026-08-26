from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    CUSTOMER = "CUSTOMER", "Customer"
    INTERNAL_SUPPORT = "INTERNAL_SUPPORT", "Internal Support"
    ADMIN = "ADMIN", "Admin"


class User(AbstractUser):
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.CUSTOMER)
    account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )
    name = models.CharField(max_length=255, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return f"{self.email} ({self.role})"

    @property
    def is_internal(self) -> bool:
        return self.role in {Role.INTERNAL_SUPPORT, Role.ADMIN}

    @property
    def is_admin_role(self) -> bool:
        return self.role == Role.ADMIN

    def allowed_account_ids(self) -> list[str] | None:
        """None means all accounts (internal/admin)."""
        if self.is_internal:
            return None
        if self.account_id:
            return [self.account.account_code]
        return []
