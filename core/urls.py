from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from accounts import views

# An ultra-lightweight ping function that executes in fractions of a millisecond
def live_ping(request):
    return HttpResponse("warm", content_type="text/plain")

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('live-ping/', live_ping, name='live_ping'),
    path('', views.login_view, name='login'),
    path('contacts/', include('contacts.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)