from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ConfiguracaoFiscalView,
    DocumentoFiscalViewSet,
    InutilizacaoNumeracaoViewSet,
    ValidarConfiguracaoFiscalView,
)


router = DefaultRouter()
router.register("documentos", DocumentoFiscalViewSet, basename="documento-fiscal")
router.register("inutilizacoes", InutilizacaoNumeracaoViewSet, basename="inutilizacao-fiscal")

urlpatterns = [
    path("configuracao/", ConfiguracaoFiscalView.as_view()),
    path("configuracao/validar/", ValidarConfiguracaoFiscalView.as_view()),
] + router.urls

