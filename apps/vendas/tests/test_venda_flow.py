import pytest
from decimal import Decimal
from django.utils import timezone
from apps.vendas.tests.factories import VendaFactory, VendaItemFactory, SessaoCaixaFactory
from apps.produtos.tests.factories import EstoqueLojaFactory, ProdutoFactory
from apps.vendas.models import Venda, VendaPagamento
from apps.financeiro.models import ContaReceber

@pytest.mark.django_db
def test_finalizar_venda_sucesso(auth_client, admin_user):
    """
    Testa o fluxo completo de finalização de uma venda e baixa de estoque.
    """
    # 1. Setup Data
    sessao = SessaoCaixaFactory(operador=admin_user)
    venda = VendaFactory(sessao=sessao, total=Decimal("50.00"), status="EM_ABERTO")

    estoque = EstoqueLojaFactory(quantidade=Decimal("10.00"), loja="Loja Principal")
    item = VendaItemFactory(
        venda=venda,
        produto=estoque.produto,
        quantidade=Decimal("2.00"),
        preco_unitario=Decimal("25.00"),
        subtotal=Decimal("50.00")
    )

    # 2. Execute Action
    payload = {
        "pagamentos": [
            {"forma": "DINHEIRO", "valor": "50.00"}
        ]
    }

    url = f"/api/vendas/{venda.id}/finalizar/"
    response = auth_client.post(url, payload, format='json')

    # 3. Assertions
    assert response.status_code == 200

    venda.refresh_from_db()
    assert venda.status == "FINALIZADA"

    estoque.refresh_from_db()
    # 10.00 inicial - 2.00 vendidos = 8.00
    assert estoque.quantidade == Decimal("8.00")

    # Verifica se criou o pagamento
    assert venda.pagamentos.count() == 1
    assert venda.pagamentos.first().forma == "DINHEIRO"


@pytest.mark.django_db
def test_finalizar_venda_nao_bloqueia_join_opcional_de_cliente(auth_client, admin_user):
    """Evita o LEFT JOIN bloqueado que causa 500 no PostgreSQL.

    O SQLite não reproduz o erro ``FOR UPDATE cannot be applied to the nullable
    side of an outer join``. Por isso a regressão também inspeciona o SQL da
    finalização e garante que a tabela de clientes não volte ao queryset
    bloqueado. A cobertura real do lock concorrente continua pertencendo aos
    testes de integração em PostgreSQL.
    """
    sessao = SessaoCaixaFactory(operador=admin_user, status='ABERTA')
    venda = VendaFactory(sessao=sessao, cliente=None, status='EM_ABERTO')
    estoque = EstoqueLojaFactory(
        quantidade=Decimal('2.00'), loja='Loja Principal', produto__preco_venda=Decimal('10.00')
    )
    VendaItemFactory(
        venda=venda,
        produto=estoque.produto,
        quantidade=Decimal('1.00'),
        preco_unitario=Decimal('10.00'),
    )

    captured_sql = []

    def capture(execute, sql, params, many, context):
        captured_sql.append(sql)
        return execute(sql, params, many, context)

    from django.db import connection

    with connection.execute_wrapper(capture):
        response = auth_client.post(
            f'/api/vendas/{venda.id}/finalizar/',
            {'pagamentos': [{'forma': 'DINHEIRO', 'valor': '10.00'}]},
            format='json',
        )

    assert response.status_code == 200
    sale_lock_queries = [
        sql for sql in captured_sql
        if 'vendas_venda' in sql.lower() and 'vendas_sessaocaixa' in sql.lower()
    ]
    assert sale_lock_queries
    assert all('clientes_cliente' not in sql.lower() for sql in sale_lock_queries)

@pytest.mark.django_db
def test_finalizar_venda_total_divergente(auth_client, admin_user):
    """
    Deve retornar 400 se o total pago não bater com o total da venda.
    """
    sessao = SessaoCaixaFactory(operador=admin_user)
    venda = VendaFactory(sessao=sessao, total=Decimal("100.00"), status="EM_ABERTO")
    VendaItemFactory(venda=venda, subtotal=Decimal("100.00"))

    payload = {
        "pagamentos": [
            {"forma": "PIX", "valor": "90.00"} # Valor errado
        ]
    }

    url = f"/api/vendas/{venda.id}/finalizar/"
    response = auth_client.post(url, payload, format='json')

    assert response.status_code == 400
    assert "não atinge" in response.data['erro']


@pytest.mark.django_db
def test_finalizar_rejeita_desconto_igual_ao_total(auth_client, admin_user):
    sessao = SessaoCaixaFactory(operador=admin_user, status='ABERTA')
    venda = VendaFactory(sessao=sessao, status='EM_ABERTO')
    produto = ProdutoFactory(preco_venda=Decimal('10.00'))
    VendaItemFactory(
        venda=venda,
        produto=produto,
        quantidade=Decimal('1.00'),
        preco_unitario=Decimal('10.00'),
    )

    response = auth_client.post(
        f'/api/vendas/{venda.id}/finalizar/',
        {'pagamentos': [{'forma': 'DINHEIRO', 'valor': '0.01'}], 'desconto': '10.00'},
        format='json',
    )

    assert response.status_code == 400
    assert 'R$0,01' in response.data['erro']
    venda.refresh_from_db()
    assert venda.status == 'EM_ABERTO'
    assert venda.pagamentos.count() == 0


@pytest.mark.django_db
def test_campos_calculados_e_estado_nao_podem_ser_forcados(auth_client, admin_user):
    sessao = SessaoCaixaFactory(operador=admin_user, status='ABERTA')
    venda = VendaFactory(
        sessao=sessao, total=Decimal('0.00'), desconto=Decimal('0.00'), status='EM_ABERTO'
    )
    produto = ProdutoFactory(preco_venda=Decimal('12.50'))

    item_response = auth_client.post('/api/venda-itens/', {
        'venda': venda.id,
        'produto': produto.id,
        'quantidade': '2.000',
        'preco_unitario': '0.01',
        'subtotal': '0.02',
    }, format='json')
    assert item_response.status_code == 201
    assert Decimal(item_response.data['preco_unitario']) == Decimal('12.50')
    assert Decimal(item_response.data['subtotal']) == Decimal('25.00')

    response = auth_client.patch(f'/api/vendas/{venda.id}/', {
        'total': '0.01',
        'desconto': '24.99',
        'status': 'FINALIZADA',
    }, format='json')
    assert response.status_code == 200

    venda.refresh_from_db()
    assert venda.total == Decimal('25.00')
    assert venda.desconto == Decimal('0.00')
    assert venda.status == 'EM_ABERTO'

    session_response = auth_client.patch(f'/api/sessoes-caixa/{sessao.id}/', {
        'fundo_inicial': '999.00',
        'status': 'FECHADA',
        'valor_contado': '999.00',
        'diferenca_caixa': '999.00',
    }, format='json')
    assert session_response.status_code == 400
    sessao.refresh_from_db()
    assert sessao.fundo_inicial == Decimal('100.00')
    assert sessao.status == 'ABERTA'
    assert sessao.valor_contado is None
    assert sessao.diferenca_caixa is None


@pytest.mark.django_db
def test_escrita_direta_de_pagamento_e_bloqueada(auth_client):
    response = auth_client.post('/api/venda-pagamentos/', {
        'venda': 1,
        'forma': 'DINHEIRO',
        'valor': '10.00',
    }, format='json')
    assert response.status_code == 405


@pytest.mark.django_db
@pytest.mark.parametrize('pagamento', [
    {'forma': 'FORMA_INEXISTENTE', 'valor': '10.00'},
    {'forma': 'DINHEIRO', 'valor': '-10.00'},
    {'forma': 'DINHEIRO', 'valor': '0.00'},
])
def test_finalizar_rejeita_pagamento_invalido(auth_client, admin_user, pagamento):
    sessao = SessaoCaixaFactory(operador=admin_user, status='ABERTA')
    venda = VendaFactory(sessao=sessao, status='EM_ABERTO')
    produto = ProdutoFactory(preco_venda=Decimal('10.00'))
    VendaItemFactory(
        venda=venda,
        produto=produto,
        quantidade=Decimal('1.00'),
        preco_unitario=Decimal('10.00'),
    )

    response = auth_client.post(
        f'/api/vendas/{venda.id}/finalizar/',
        {'pagamentos': [pagamento]},
        format='json',
    )
    assert response.status_code == 400
    venda.refresh_from_db()
    assert venda.status == 'EM_ABERTO'
    assert venda.pagamentos.count() == 0


@pytest.mark.django_db
def test_operador_nao_muta_caixa_ou_venda_de_outro_operador(auth_client):
    sessao = SessaoCaixaFactory(status='ABERTA')
    venda = VendaFactory(sessao=sessao, status='EM_ABERTO')
    produto = ProdutoFactory(preco_venda=Decimal('10.00'))

    item_response = auth_client.post('/api/venda-itens/', {
        'venda': venda.id,
        'produto': produto.id,
        'quantidade': '1.000',
    }, format='json')
    assert item_response.status_code == 400

    final_response = auth_client.post(
        f'/api/vendas/{venda.id}/finalizar/',
        {'pagamentos': [{'forma': 'DINHEIRO', 'valor': '10.00'}]},
        format='json',
    )
    assert final_response.status_code == 403

    close_response = auth_client.post(
        f'/api/sessoes-caixa/{sessao.id}/fechar/',
        {'valor_contado': '0.00'},
        format='json',
    )
    assert close_response.status_code == 403


@pytest.mark.django_db
def test_finalizacao_sequencial_nao_duplica_pagamento_ou_baixa(auth_client, admin_user):
    sessao = SessaoCaixaFactory(operador=admin_user, status='ABERTA')
    venda = VendaFactory(sessao=sessao, status='EM_ABERTO')
    estoque = EstoqueLojaFactory(
        quantidade=Decimal('5.00'), loja='Loja Principal', produto__preco_venda=Decimal('10.00')
    )
    VendaItemFactory(
        venda=venda,
        produto=estoque.produto,
        quantidade=Decimal('1.00'),
        preco_unitario=Decimal('10.00'),
    )
    payload = {'pagamentos': [{'forma': 'DINHEIRO', 'valor': '10.00'}]}
    url = f'/api/vendas/{venda.id}/finalizar/'

    primeira = auth_client.post(url, payload, format='json')
    segunda = auth_client.post(url, payload, format='json')

    assert primeira.status_code == 200
    assert segunda.status_code == 400
    estoque.refresh_from_db()
    assert estoque.quantidade == Decimal('4.00')
    assert venda.pagamentos.count() == 1


@pytest.mark.django_db
def test_cancelar_fiado_remove_pendente_e_preserva_recebido(auth_client, admin_user):
    sessao = SessaoCaixaFactory(operador=admin_user, status='ABERTA')
    venda = VendaFactory(sessao=sessao, status='FINALIZADA')
    origem = {
        'descricao': f'Venda FIADO #{venda.id}',
        'observacoes': f'Originada da Venda #{venda.id} no PDV.',
        'cliente_nome': 'Cliente teste',
        'valor': Decimal('10.00'),
        'vencimento': timezone.localdate(),
    }
    pendente = ContaReceber.objects.create(status='PENDENTE', **origem)
    recebido = ContaReceber.objects.create(
        status='RECEBIDO', data_recebimento=timezone.localdate(), **origem
    )

    response = auth_client.post(
        f'/api/vendas/{venda.id}/cancelar/',
        {'motivo': 'Cliente desistiu da compra'},
        format='json',
    )

    assert response.status_code == 200
    pendente.refresh_from_db()
    recebido.refresh_from_db()
    assert pendente.is_deleted is True
    assert ContaReceber.objects.filter(pk=pendente.pk).exists() is False
    assert recebido.is_deleted is False
    assert ContaReceber.objects.filter(pk=recebido.pk).exists() is True


@pytest.mark.django_db
def test_rota_salvar_orcamento_nao_existe(auth_client, admin_user):
    sessao = SessaoCaixaFactory(operador=admin_user, status='ABERTA')
    venda = VendaFactory(sessao=sessao, status='EM_ABERTO')

    response = auth_client.post(
        f'/api/vendas/{venda.id}/salvar-orcamento/', {}, format='json'
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_fechar_caixa_exige_conferencia_e_calcula_diferenca(auth_client, admin_user):
    sessao = SessaoCaixaFactory(
        operador=admin_user,
        fundo_inicial=Decimal('100.00'),
        status='ABERTA',
    )
    venda = VendaFactory(sessao=sessao, total=Decimal('50.00'), status='FINALIZADA')
    VendaPagamento.objects.create(venda=venda, forma='DINHEIRO', valor=Decimal('50.00'))

    sem_valor = auth_client.post(f'/api/sessoes-caixa/{sessao.id}/fechar/', {}, format='json')
    assert sem_valor.status_code == 400
    assert 'valor contado' in sem_valor.data['erro'].lower()

    resposta = auth_client.post(
        f'/api/sessoes-caixa/{sessao.id}/fechar/',
        {'valor_contado': '148.00'},
        format='json',
    )
    assert resposta.status_code == 200
    assert Decimal(str(resposta.data['resumo']['valor_esperado'])) == Decimal('150.00')
    assert Decimal(str(resposta.data['resumo']['diferenca'])) == Decimal('-2.00')

    sessao.refresh_from_db()
    assert sessao.status == 'FECHADA'
    assert sessao.valor_contado == Decimal('148.00')
    assert sessao.diferenca_caixa == Decimal('-2.00')


@pytest.mark.django_db
def test_bipar_mesmo_produto_soma_na_mesma_linha(auth_client, admin_user):
    sessao = SessaoCaixaFactory(operador=admin_user, status='ABERTA')
    venda = VendaFactory(sessao=sessao, total=Decimal('0.00'), status='EM_ABERTO')
    produto = ProdutoFactory(preco_venda=Decimal('5.00'))

    for _ in range(2):
        response = auth_client.post('/api/venda-itens/', {
            'venda': venda.id,
            'produto': produto.id,
            'quantidade': '1.000',
        }, format='json')
        assert response.status_code == 201

    assert venda.itens.count() == 1
    item = venda.itens.get()
    assert item.quantidade == Decimal('2.000')
    venda.refresh_from_db()
    assert venda.total == Decimal('10.00')
