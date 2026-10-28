from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import MeuPerfilView, UsuarioViewSet


router = DefaultRouter()
router.register('usuarios', UsuarioViewSet, basename='usuario')

urlpatterns = [path('auth/me/', MeuPerfilView.as_view(), name='meu-perfil')] + router.urls

