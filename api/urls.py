from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BookViewSet,
    TelegramLiveLessonViewSet,
    VideoChannelViewSet,
    VideoLessonViewSet,
    VideoSeriesViewSet,
    health,
    hifz_evaluate,
    lesson_sections,
    livekit_token,
    live_teacher_lookup,
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
    path('quran-meal-notes/', quran_meal_notes, name='quran-meal-notes'),
    path('support/', support_create, name='support-create'),
    path('quran-qa/', quran_qa_create, name='quran-qa-create'),
    path('youtube-title/', youtube_title_lookup, name='youtube-title'),
    path('video-search/', video_search, name='video-search'),
    path('lesson-sections/', lesson_sections, name='lesson-sections'),
    path('hifz/evaluate/', hifz_evaluate, name='hifz-evaluate'),
    path('live/token/', livekit_token, name='livekit-token'),
    path('live/teacher/', live_teacher_lookup, name='live-teacher-lookup'),
    path('', include(router.urls)),
]
