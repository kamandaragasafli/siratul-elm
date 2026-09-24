from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BookViewSet,
    TelegramLiveLessonViewSet,
    VideoChannelViewSet,
    VideoLessonViewSet,
    VideoSeriesViewSet,
    deploy_ixlasla_api,
    health,
    hifz_evaluate,
    lesson_sections,
    live_session_end,
    live_session_start,
    livekit_token,
    livekit_status,
    live_teacher_lookup,
    push_register,
    quran_meal_notes,
    quran_qa_create,
    support_create,
    video_search,
    youtube_title_lookup,
)

router = DefaultRouter()
router.register('books', BookViewSet, basename='book')
router.register('live-lessons', TelegramLiveLessonViewSet, basename='live-lesson')
router.register('channels', VideoChannelViewSet, basename='channel')
router.register('series', VideoSeriesViewSet, basename='series')
router.register('lessons', VideoLessonViewSet, basename='lesson')

urlpatterns = [
    path('health/', health, name='health'),
    path('deploy-ixlasla/', deploy_ixlasla_api, name='deploy-ixlasla'),
    path('quran-meal-notes/', quran_meal_notes, name='quran-meal-notes'),
    path('support/', support_create, name='support-create'),
    path('quran-qa/', quran_qa_create, name='quran-qa-create'),
    path('youtube-title/', youtube_title_lookup, name='youtube-title'),
    path('video-search/', video_search, name='video-search'),
    path('lesson-sections/', lesson_sections, name='lesson-sections'),
    path('hifz/evaluate/', hifz_evaluate, name='hifz-evaluate'),
    path('live/token/', livekit_token, name='livekit-token'),
    path('live/status/', livekit_status, name='livekit-status'),
    path('live/teacher/', live_teacher_lookup, name='live-teacher-lookup'),
    path('live/session/start/', live_session_start, name='live-session-start'),
    path('live/session/end/', live_session_end, name='live-session-end'),
    path('push/register/', push_register, name='push-register'),
    path('', include(router.urls)),
]
