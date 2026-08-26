from rest_framework import generics
from rest_framework.exceptions import PermissionDenied

from apps.users.permissions import user_context

from .models import Account
from .serializers import AccountSerializer


class AccountListView(generics.ListAPIView):
    serializer_class = AccountSerializer

    def get_queryset(self):
        ctx = user_context(self.request.user)
        qs = Account.objects.all()
        allowed = ctx["allowed_account_ids"]
        if allowed is not None:
            qs = qs.filter(account_code__in=allowed)
        return qs


class AccountDetailView(generics.RetrieveAPIView):
    serializer_class = AccountSerializer
    lookup_field = "account_code"

    def get_queryset(self):
        return Account.objects.all()

    def get_object(self):
        obj = super().get_object()
        ctx = user_context(self.request.user)
        allowed = ctx["allowed_account_ids"]
        if allowed is not None and obj.account_code not in allowed:
            raise PermissionDenied("AUTHORIZATION_DENIED")
        return obj
