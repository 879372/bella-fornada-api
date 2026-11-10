from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ConfiguracaoFiscalView, DocumentoFiscalViewSet, ValidarConfiguracaoFiscalView


router = DefaultRouter()
router.register("documentos", DocumentoFiscalViewSet, basename="documento-fiscal")

urlpatterns = [
    path("configuracao/", ConfiguracaoFiscalView.as_view()),
    path("configuracao/validar/", ValidarConfiguracaoFiscalView.as_view()),
] + router.urls

