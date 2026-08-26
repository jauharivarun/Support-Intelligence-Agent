from django.urls import path

from .views import AccountDetailView, AccountListView

urlpatterns = [
    path("", AccountListView.as_view()),
    path("<str:account_code>/", AccountDetailView.as_view()),
]
