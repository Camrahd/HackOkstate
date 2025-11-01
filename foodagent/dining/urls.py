from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RecommendationAPI, MenuAPI, CartAPI, AgentAPI, landing

router = DefaultRouter()
router.register('menu', MenuAPI, basename='menu')

urlpatterns = [
    path('', landing, name='landing'),
    path('api/recommendations/', RecommendationAPI.as_view()),
    path('api/cart/', CartAPI.as_view()),
    path('api/agent/', AgentAPI.as_view()),
    path('api/', include(router.urls)),
]