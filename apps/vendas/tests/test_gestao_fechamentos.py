from decimal import Decimal

import pytest

from apps.vendas.models import OperacaoCaixa, VendaPagamento
from apps.vendas.tests.factories import SessaoCaixaFactory, VendaFactory

pytestmark = pytest.mark.django_db


def test_gestao_concilia_liquido_pagamentos_e_movimentacoes(auth_client):
    caixa = SessaoCaixaFactory(fundo_inicial=100)
    venda = VendaFactory(sessao=caixa, status='FINALIZADA', total=100, desconto=10)
    for forma, valor in [('DINHEIRO', 20), ('DINHEIRO', 10), ('PIX', 60)]:
        VendaPagamento.objects.create(venda=venda, forma=forma, valor=valor)
    cancelada = VendaFactory(sessao=caixa, status='CANCELADA', total=500)
    VendaPagamento.objects.create(venda=cancelada, forma='DINHEIRO', valor=500)
    VendaFactory(sessao=caixa, status='EM_ABERTO', total=20)
    VendaFactory(sessao=caixa, status='ORCAMENTO', total=30)
    VendaFactory(sessao=caixa, status='FINALIZADA', total=999, is_deleted=True)
    OperacaoCaixa.objects.create(sessao=caixa, tipo='SANGRIA', valor=15, motivo='Retirada')
    OperacaoCaixa.objects.create(sessao=caixa, tipo='SUPRIMENTO', valor=5)
    OperacaoCaixa.objects.create(sessao=caixa, tipo='SANGRIA', valor=999, is_deleted=True)
    response = auth_client.get('/api/sessoes-caixa/gestao/')
    assert response.status_code == 200
    item = response.data['results'][0]
    resumo = item['resumo']
    assert resumo['quantidade_total'] == 4
    assert resumo['quantidade_vendas'] == 1
    assert resumo['quantidade_abertas'] == 1
    assert resumo['quantidade_canceladas'] == 1
    assert resumo['quantidade_orcamentos'] == 1
    assert Decimal(resumo['total_liquido']) == 90
    assert Decimal(resumo['descontos']) == 10
    assert Decimal(resumo['saldo_esperado']) == 120
    assert resumo['por_forma']['DINHEIRO']['quantidade'] == 1
    assert Decimal(resumo['por_forma']['DINHEIRO']['valor']) == 30
    assert Decimal(resumo['por_forma']['PIX']['valor']) == 60
    assert len(resumo['operacoes']) == 2
    assert item['valor_contado'] is None
    assert item['diferenca_caixa'] is None


def test_gestao_inclui_todas_as_vendas_independente_da_paginacao(auth_client):
    caixa = SessaoCaixaFactory()
    VendaFactory.create_batch(55, sessao=caixa, status='FINALIZADA', total=10, desconto=1)
    resumo = auth_client.get('/api/sessoes-caixa/gestao/').data['results'][0]['resumo']
    assert resumo['quantidade_vendas'] == 55
    assert Decimal(resumo['total_liquido']) == 495


def test_gestao_filtra_status_operador_e_periodo(auth_client):
    caixa = SessaoCaixaFactory(status='FECHADA', valor_contado=90, diferenca_caixa=-10)
    SessaoCaixaFactory(status='ABERTA')
    params = {'status': 'FECHADA', 'q': caixa.operador.username, 'data_inicio': '2020-01-01', 'data_fim': '2099-12-31'}
    response = auth_client.get('/api/sessoes-caixa/gestao/', params)
    assert response.data['count'] == 1
    assert Decimal(response.data['results'][0]['diferenca_caixa']) == -10
    params['data_fim'] = '2020-01-02'
    assert auth_client.get('/api/sessoes-caixa/gestao/', params).data['count'] == 0


def test_gestao_exige_autenticacao(api_client):
    assert api_client.get('/api/sessoes-caixa/gestao/').status_code in (401, 403)
