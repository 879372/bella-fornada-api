from rest_framework.routers import DefaultRouter

from .views import DocumentoFiscalViewSet


router = DefaultRouter()
router.register("documentos", DocumentoFiscalViewSet, basename="documento-fiscal")

urlpatterns = router.urls

