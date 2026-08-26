from django.db.models import Count
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.observability.models import ObservabilityEvent
from apps.users.permissions import IsInternalOrAdmin


class ObservabilitySummaryView(APIView):
    permission_classes = [IsInternalOrAdmin]

    def get(self, request):
        counts = {
            row["event_type"]: row["c"]
            for row in ObservabilityEvent.objects.values("event_type").annotate(c=Count("id"))
        }
        recent = list(
            ObservabilityEvent.objects.order_by("-created_at")[:50].values(
                "id",
                "event_type",
                "tool_name",
                "status",
                "duration_ms",
                "created_at",
            )
        )
        return Response({"counts": counts, "recent": recent})
