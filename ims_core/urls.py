import os
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from django.http import HttpResponse, FileResponse

DIST_DIR = os.path.join(settings.BASE_DIR, 'frontend', 'dist')

def serve_spa(request):
    index_path = os.path.join(DIST_DIR, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(open(index_path, 'rb'), content_type='text/html')
    return HttpResponse(
        "<h3>Frontend build not found. Please build frontend with 'npm run build' inside /frontend.</h3>", 
        status=404
    )

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/index.py', serve_spa),
    path('api/', include('inventory.urls')),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^assets/(?P<path>.*)$', serve, {'document_root': os.path.join(DIST_DIR, 'assets')}),
    path('favicon.svg', serve, {'document_root': DIST_DIR, 'path': 'favicon.svg'}),
    path('icons.svg', serve, {'document_root': DIST_DIR, 'path': 'icons.svg'}),
    path('index.html', serve_spa),
    path('', serve_spa),
    re_path(r'^(?!api|admin|media).*$', serve_spa),
]


