from django.urls import path

from .views import ObservabilitySummaryView

urlpatterns = [
    path("", ObservabilitySummaryView.as_view()),
]
