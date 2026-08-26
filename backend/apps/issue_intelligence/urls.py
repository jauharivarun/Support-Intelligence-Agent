from django.urls import path

from .views import IssueIntelligenceView

urlpatterns = [
    path("", IssueIntelligenceView.as_view()),
]
