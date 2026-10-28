from rest_framework.routers import DefaultRouter
from .views import ContaPagarViewSet, ContaReceberViewSet, CategoriaFinanceiraViewSet

router = DefaultRouter()
router.register(r'categorias', CategoriaFinanceiraViewSet, basename='categoria-financeira')
router.register(r'contas-pagar', ContaPagarViewSet, basename='conta-pagar')
router.register(r'contas-receber', ContaReceberViewSet, basename='conta-receber')

urlpatterns = router.urls
