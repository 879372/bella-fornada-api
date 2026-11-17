from decimal import Decimal

import pytest

from apps.produtos.models import MovimentacaoEstoque
from apps.produtos.tests.factories import EstoqueLojaFactory
from apps.vendas.models import SessaoCaixa, VendaPagamento
from apps.vendas.tests.factories import SessaoCaixaFactory, VendaFactory, VendaItemFactory

pytestmark = pytest.mark.django_db


def test_fechar_cancela_apenas_abertas_da_sessao_e_registra_auditoria(auth_client, admin_user):
    caixa = SessaoCaixaFactory(operador=admin_user, fundo_inicial=100)
    estoque = EstoqueLojaFactory(quantidade=10)
    aberta = VendaFactory(sessao=caixa, status='EM_ABERTO')
    VendaItemFactory(venda=aberta, produto=estoque.produto, quantidade=2, preco_unitario=10)
    vazia = VendaFactory(sessao=caixa, status='EM_ABERTO')
    finalizada = VendaFactory(sessao=caixa, status='FINALIZADA', total=50, desconto=5)
    VendaPagamento.objects.create(venda=finalizada, forma='DINHEIRO', valor=45)
    cancelada = VendaFactory(sessao=caixa, status='CANCELADA', motivo_cancelamento='Motivo anterior')
    orcamento = VendaFactory(sessao=caixa, status='ORCAMENTO')
    outra = VendaFactory(status='EM_ABERTO')
    movimentos = MovimentacaoEstoque.objects.count()
    response = auth_client.post(f'/api/sessoes-caixa/{caixa.pk}/fechar/', {'valor_contado': '140.00'}, format='json')
    assert response.status_code == 200
    assert response.data['resumo']['quantidade_vendas_canceladas'] == 2
    assert response.data['resumo']['quantidade_vendas'] == 1
    for venda in [aberta, vazia]:
        venda.refresh_from_db()
        assert venda.status == 'CANCELADA'
        assert venda.cancelada_por_id == admin_user.pk
        assert venda.cancelada_em is not None
        assert 'fechamento do caixa' in venda.motivo_cancelamento
    for venda, esperado in [(finalizada, 'FINALIZADA'), (cancelada, 'CANCELADA'), (orcamento, 'ORCAMENTO'), (outra, 'EM_ABERTO')]:
        venda.refresh_from_db()
        assert venda.status == esperado
    assert cancelada.motivo_cancelamento == 'Motivo anterior'
    estoque.refresh_from_db()
    assert estoque.quantidade == 10
    assert MovimentacaoEstoque.objects.count() == movimentos
    caixa.refresh_from_db()
    assert caixa.status == 'FECHADA'
    assert caixa.diferenca_caixa == Decimal('-5')


def test_falha_no_fechamento_desfaz_cancelamentos(auth_client, admin_user, monkeypatch):
    caixa = SessaoCaixaFactory(operador=admin_user)
    venda = VendaFactory(sessao=caixa, status='EM_ABERTO')
    original = SessaoCaixa.save

    def falhar(self, *args, **kwargs):
        if self.status == 'FECHADA':
            raise RuntimeError('Falha simulada')
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SessaoCaixa, 'save', falhar)
    with pytest.raises(RuntimeError, match='Falha simulada'):
        auth_client.post(f'/api/sessoes-caixa/{caixa.pk}/fechar/', {'valor_contado': '100.00'}, format='json')
    caixa.refresh_from_db()
    venda.refresh_from_db()
    assert caixa.status == 'ABERTA'
    assert venda.status == 'EM_ABERTO'
    assert venda.cancelada_em is None


def test_valor_invalido_nao_cancela_vendas(auth_client, admin_user):
    caixa = SessaoCaixaFactory(operador=admin_user)
    venda = VendaFactory(sessao=caixa, status='EM_ABERTO')
    response = auth_client.post(f'/api/sessoes-caixa/{caixa.pk}/fechar/', {'valor_contado': '-1'}, format='json')
    assert response.status_code == 400
    venda.refresh_from_db()
    assert venda.status == 'EM_ABERTO'
