from rest_framework import serializers

from .models import Ticket


class TicketSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.account_code", read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "ticket_id",
            "account_code",
            "created_at",
            "status",
            "subject",
            "description",
            "channel",
            "assigned_to",
            "last_customer_message_at",
            "historical_resolution",
            "severity",
            "category",
        ]
