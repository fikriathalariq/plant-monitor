from django.contrib import admin
from django.urls import re_path, path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from monitoring.views import CustomLoginView, url_auto_login
from django.views.static import serve      # <--- Tambah ini
from monitoring.api import api             # <--- Import Django Ninja API


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", api.urls),

    path("login/", CustomLoginView.as_view(), name="login"),
    path("login/<str:username>/<path:password>/", url_auto_login, name="url_auto_login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("", include("monitoring.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Tambahkan kode ini di bagian paling bawah (di luar list urlpatterns)
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {
        'document_root': settings.MEDIA_ROOT,
    }),
]