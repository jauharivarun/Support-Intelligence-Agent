from rest_framework import serializers

from .models import Order


class OrderSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.account_code", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_id",
            "account_code",
            "carrier",
            "status",
            "booked_at",
            "pickup_window_start",
            "pickup_window_end",
            "pickup_actual_at",
            "shipment_fee_inr",
            "carrier_fault",
            "customer_fault",
            "cancellation_requested_at",
            "notes",
        ]
