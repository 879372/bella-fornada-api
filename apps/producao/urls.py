from rest_framework.routers import DefaultRouter

from .views import OrdemProducaoViewSet, PerdaProducaoViewSet, ReceitaViewSet


router = DefaultRouter()
router.register('receitas', ReceitaViewSet, basename='receita')
router.register('ordens', OrdemProducaoViewSet, basename='ordem-producao')
router.register('perdas', PerdaProducaoViewSet, basename='perda-producao')

urlpatterns = router.urls

