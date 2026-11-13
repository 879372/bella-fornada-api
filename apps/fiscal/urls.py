from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CartaCorrecaoFiscalViewSet,
    ConfiguracaoFiscalView,
    DocumentoFiscalViewSet,
    InutilizacaoNumeracaoViewSet,
    MonitorFiscalView,
    ValidarConfiguracaoFiscalView,
)


router = DefaultRouter()
router.register("documentos", DocumentoFiscalViewSet, basename="documento-fiscal")
router.register("inutilizacoes", InutilizacaoNumeracaoViewSet, basename="inutilizacao-fiscal")
router.register("cartas-correcao", CartaCorrecaoFiscalViewSet, basename="carta-correcao-fiscal")

urlpatterns = [
    path("configuracao/", ConfiguracaoFiscalView.as_view()),
    path("configuracao/validar/", ValidarConfiguracaoFiscalView.as_view()),
    path("monitor/", MonitorFiscalView.as_view()),
] + router.urls

