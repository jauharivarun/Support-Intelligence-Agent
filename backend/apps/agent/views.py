from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agent.models import ChatSession
from apps.agent.orchestrator import run_agent
from apps.agent.serializers import (
    ChatAskSerializer,
    ChatSessionListSerializer,
    ChatSessionSerializer,
)


class SessionListCreateView(generics.ListCreateAPIView):
    serializer_class = ChatSessionListSerializer

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SessionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ChatSessionSerializer

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method in {"PUT", "PATCH"}:
            return ChatSessionListSerializer
        return ChatSessionSerializer


class ChatAskView(APIView):
    def post(self, request):
        ser = ChatAskSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        session_id = ser.validated_data.get("session_id")
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, user=request.user)
            except ChatSession.DoesNotExist:
                return Response({"detail": "session not found"}, status=404)
        else:
            session = ChatSession.objects.create(user=request.user)

        result = run_agent(request.user, session, ser.validated_data["message"])
        return Response(result, status=status.HTTP_200_OK)
