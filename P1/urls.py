from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.shortcuts import redirect
from django.views.static import serve
from app.pwa_portals import pwa_manifest
from app.pwa_icons import pwa_icon, connect_signals
from app.pwa_offline import offline_page as pwa_offline_page
from app.image_tools import thumb_view

connect_signals()   # logo badalne par PWA icon cache saaf

# Custom Handlers
handler404 = 'app.views.custom_page_not_found'
handler500 = 'app.views.custom_server_error'

urlpatterns = [
    # Admin Panel
    path('admin/', admin.site.urls),
    
    # Chhoti (compressed) tasveerein
    path('img/<int:w>/<path:path>', thumb_view, name='img_thumb'),

    # Frontend (All app URLs)
    path('', include('app.urls')),
    
    # CEO Module
    path('ceo/', include('ceo_module.urls')),
    
    # Progressive Web App (PWA) URLs
    path('pwa/manifest/<slug:portal>.json', pwa_manifest, name='pwa_manifest'),
    path('pwa/icon/<slug:portal>/<slug:name>.png', pwa_icon, name='pwa_icon'),
    path('offline/', pwa_offline_page, name='pwa_offline_page'),   # branded offline page (pwa.urls se pehle)
    path('', include('pwa.urls')),
    
    # Redirect /accounts/login/ to /login/
    path('accounts/login/', lambda request: redirect('/login/')),
    
    # GET logout redirect (Django 5.x fix)
    path('accounts/logout/', lambda request: redirect('/logout-redirect/')),
    path('logout-redirect/', lambda request: redirect('/login/'), name='logout_redirect'),
]

# Force-serve media and static files in CI/CD Runner & Cloudflare Tunnel
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
]
