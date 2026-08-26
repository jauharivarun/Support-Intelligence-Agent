from rest_framework import generics
from rest_framework.exceptions import PermissionDenied

from apps.users.permissions import user_context

from .models import Order
from .serializers import OrderSerializer


def scoped_orders(user):
    ctx = user_context(user)
    qs = Order.objects.select_related("account")
    allowed = ctx["allowed_account_ids"]
    if allowed is not None:
        qs = qs.filter(account__account_code__in=allowed)
    return qs


class OrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer

    def get_queryset(self):
        qs = scoped_orders(self.request.user)
        account = self.request.query_params.get("account_id")
        if account:
            ctx = user_context(self.request.user)
            allowed = ctx["allowed_account_ids"]
            if allowed is not None and account not in allowed:
                raise PermissionDenied("AUTHORIZATION_DENIED")
            qs = qs.filter(account__account_code=account)
        return qs


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    lookup_field = "order_id"

    def get_queryset(self):
        return scoped_orders(self.request.user)
