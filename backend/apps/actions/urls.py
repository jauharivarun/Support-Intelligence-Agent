from django.urls import path

from .views import PendingActionCancelView, PendingActionConfirmView, PendingActionDetailView

urlpatterns = [
    path("<int:pk>/", PendingActionDetailView.as_view()),
    path("<int:pk>/confirm/", PendingActionConfirmView.as_view()),
    path("<int:pk>/cancel/", PendingActionCancelView.as_view()),
]
