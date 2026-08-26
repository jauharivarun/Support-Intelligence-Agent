from django.urls import path

from .views import OrderDetailView, OrderListView

urlpatterns = [
    path("", OrderListView.as_view()),
    path("<str:order_id>/", OrderDetailView.as_view()),
]
