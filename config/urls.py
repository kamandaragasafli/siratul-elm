from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from api.dashboard import (
    dashboard,
    panel_books,
    panel_chapter_ai_fix,
    panel_chapter_preview,
    panel_channels,
    panel_chapters,
    panel_home,
    panel_lessons,
    panel_live_lessons,
    panel_logout,
    panel_meal_notes,
    panel_support,
)

urlpatterns = [
    path('', panel_home, name='panel-home'),
    path('dashboard/', dashboard, name='dashboard'),
    path('panel/books/', panel_books, name='panel-books'),
    path('panel/chapters/', panel_chapters, name='panel-chapters'),
    path('panel/chapters/preview/', panel_chapter_preview, name='panel-chapter-preview'),
    path('panel/chapters/ai-fix/', panel_chapter_ai_fix, name='panel-chapter-ai-fix'),
    path('panel/channels/', panel_channels, name='panel-channels'),
    path('panel/lessons/', panel_lessons, name='panel-lessons'),
    path('panel/live-lessons/', panel_live_lessons, name='panel-live-lessons'),
    path('panel/meal-notes/', panel_meal_notes, name='panel-meal-notes'),
    path('panel/support/', panel_support, name='panel-support'),
    path('panel/logout/', panel_logout, name='panel-logout'),
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
