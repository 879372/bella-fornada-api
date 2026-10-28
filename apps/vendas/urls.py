from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import (
    SessaoCaixaViewSet, VendaViewSet, VendaItemViewSet,
    VendaPagamentoViewSet, OperacaoCaixaViewSet, comprovante_venda_publico
)

router = DefaultRouter()
router.register(r'sessoes-caixa', SessaoCaixaViewSet, basename='sessao-caixa')
router.register(r'vendas', VendaViewSet, basename='venda')
router.register(r'venda-itens', VendaItemViewSet, basename='venda-item')
router.register(r'venda-pagamentos', VendaPagamentoViewSet, basename='venda-pagamento')
router.register(r'operacoes-caixa', OperacaoCaixaViewSet, basename='operacao-caixa')

urlpatterns = [
    path('comprovante/<uuid:id_externo>/', comprovante_venda_publico, name='comprovante_venda_publico'),
] + router.urls
