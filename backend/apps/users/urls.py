from django.urls import path

from .views import DemoUsersView, LoginView, MeView

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("me/", MeView.as_view(), name="me"),
    path("demo-users/", DemoUsersView.as_view(), name="demo-users"),
]
