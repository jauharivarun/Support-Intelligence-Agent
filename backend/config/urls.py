from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from config.health import health

urlpatterns = [
    path("health/", health),
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.users.urls")),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/tickets/", include("apps.tickets.urls")),
    path("api/documents/", include("apps.documents.urls")),
    path("api/agent/", include("apps.agent.urls")),
    path("api/actions/", include("apps.actions.urls")),
    path("api/issue-intelligence/", include("apps.issue_intelligence.urls")),
    path("api/observability/", include("apps.observability.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
