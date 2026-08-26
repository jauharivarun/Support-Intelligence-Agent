from django.urls import path

from .views import DocumentDetailView, DocumentListView, DocumentUploadView

urlpatterns = [
    path("", DocumentListView.as_view()),
    path("upload/", DocumentUploadView.as_view()),
    path("<int:pk>/", DocumentDetailView.as_view()),
]
