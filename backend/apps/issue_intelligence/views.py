from rest_framework.response import Response
from rest_framework.views import APIView

from apps.issue_intelligence.service import build_dashboard
from apps.users.permissions import IsInternalOrAdmin


class IssueIntelligenceView(APIView):
    permission_classes = [IsInternalOrAdmin]

    def get(self, request):
        return Response(build_dashboard())
