from rest_framework.routers import DefaultRouter
from .views import ProdutoViewSet, GrupoViewSet

router = DefaultRouter()
router.register(r'produtos', ProdutoViewSet, basename='produto')
router.register(r'grupos', GrupoViewSet, basename='grupo')

urlpatterns = router.urls
