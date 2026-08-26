from django.urls import path

from .views import TicketDetailView, TicketListView

urlpatterns = [
    path("", TicketListView.as_view()),
    path("<str:ticket_id>/", TicketDetailView.as_view()),
]
