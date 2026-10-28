from rest_framework.routers import DefaultRouter
from .views import NotaCompraViewSet

router = DefaultRouter()
router.register(r'compras', NotaCompraViewSet, basename='compra')

urlpatterns = router.urls
