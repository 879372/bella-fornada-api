from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import (
    ConfiguracaoBalancaView,
    ExportarCargaBalancaView,
    GrupoViewSet,
    ProdutoViewSet,
)

router = DefaultRouter()
router.register(r'produtos', ProdutoViewSet, basename='produto')
router.register(r'grupos', GrupoViewSet, basename='grupo')

urlpatterns = [
    path('balancas/configuracao/', ConfiguracaoBalancaView.as_view()),
    path('balancas/exportar/', ExportarCargaBalancaView.as_view()),
] + router.urls
