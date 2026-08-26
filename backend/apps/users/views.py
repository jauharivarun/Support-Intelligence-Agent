from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import EmailTokenObtainPairSerializer, UserSerializer


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = EmailTokenObtainPairSerializer


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class DemoUsersView(APIView):
    """List demo credentials for local login UX (no secrets beyond demo passwords)."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            [
                {
                    "label": "Northstar Customer",
                    "email": "northstar@demo.local",
                    "password": "demo1234",
                    "role": "CUSTOMER",
                },
                {
                    "label": "LumenWorks Customer",
                    "email": "lumenworks@demo.local",
                    "password": "demo1234",
                    "role": "CUSTOMER",
                },
                {
                    "label": "Internal Support",
                    "email": "support@demo.local",
                    "password": "demo1234",
                    "role": "INTERNAL_SUPPORT",
                },
                {
                    "label": "Admin",
                    "email": "admin@demo.local",
                    "password": "demo1234",
                    "role": "ADMIN",
                },
            ]
        )
