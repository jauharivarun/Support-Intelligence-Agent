from rest_framework import serializers

from .models import Account


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = [
            "id",
            "account_code",
            "name",
            "plan",
            "status",
            "csm",
            "premium_support",
            "notes",
        ]
