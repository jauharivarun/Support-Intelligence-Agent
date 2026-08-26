from django.urls import path

from .views import ChatAskView, SessionDetailView, SessionListCreateView

urlpatterns = [
    path("sessions/", SessionListCreateView.as_view()),
    path("sessions/<int:pk>/", SessionDetailView.as_view()),
    path("chat/", ChatAskView.as_view()),
]
