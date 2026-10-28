from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.delivery.models import BairroEntrega, ConfiguracaoDelivery, PedidoDelivery
from apps.produtos.tests.factories import EstoqueLojaFactory, ProdutoFactory
from apps.vendas.models import SessaoCaixa


@pytest.fixture
def loja_aberta(db):
    configuracao = ConfiguracaoDelivery.atual()
    # Início igual ao fim = aberto o dia inteiro.
    configuracao.horarios_funcionamento = {
        str(dia): {'aberto': True, 'inicio': '00:00', 'fim': '00:00'} for dia in range(7)
    }
    configuracao.save()
    return configuracao


def _payload(produto, bairro):
    return {
        'nome_cliente': 'Maria',
        'telefone_cliente': '85999990000',
        'fulfillment': 'ENTREGA',
        'payment_method': 'DINHEIRO',
        'bairro': bairro.id,
        'bairro_outro': '',
        'cep': '60000000',
        'endereco': 'Rua A',
        'numero': '10',
        'complemento': '',
        'referencia': '',
        'cidade': 'Fortaleza',
        'uf': 'CE',
        'troco_para': None,
        'observacoes': '',
        'itens': [{'produto': produto.id, 'quantidade': 2, 'complementos': [], 'observacoes': ''}],
    }


def test_fluxo_completo_do_pedido_online(auth_client, admin_user, loja_aberta):
    publico = APIClient()
    produto = ProdutoFactory(preco_venda=Decimal('5.00'), disponivel_delivery=True)
    EstoqueLojaFactory(produto=produto, quantidade=Decimal('50'))
    bairro = BairroEntrega.objects.create(nome='Centro', taxa_entrega=Decimal('4.00'))

    menu = publico.get(f'/api/public/{loja_aberta.slug}/menu/')
    assert menu.status_code == 200

    criado = publico.post(
        f'/api/public/{loja_aberta.slug}/orders/',
        _payload(produto, bairro),
        format='json',
        HTTP_IDEMPOTENCY_KEY='pedido-teste-1',
    )
    assert criado.status_code == 201, criado.data
    assert Decimal(str(criado.data['total'])) == Decimal('14.00')
    assert criado.data['tracking_url'].endswith(f"/acompanhar/{criado.data['rastreamento_token']}")
    pedido_id = criado.data['id']

    fila = auth_client.get('/api/delivery/pedidos/')
    assert fila.status_code == 200

    for status in ('CONFIRMADO', 'EM_PREPARO', 'PRONTO', 'SAIU_ENTREGA'):
        resposta = auth_client.post(
            f'/api/delivery/pedidos/{pedido_id}/alterar-status/', {'status': status}, format='json'
        )
        assert resposta.status_code == 200, resposta.data

    SessaoCaixa.objects.create(operador=admin_user)
    concluido = auth_client.post(
        f'/api/delivery/pedidos/{pedido_id}/alterar-status/',
        {'status': 'CONCLUIDO', 'pagamento_confirmado': True, 'payment_method': 'DINHEIRO'},
        format='json',
    )
    assert concluido.status_code == 200, concluido.data
    pedido = PedidoDelivery.objects.get(pk=pedido_id)
    assert pedido.status == PedidoDelivery.Status.CONCLUIDO
    assert pedido.venda.status == 'FINALIZADA'

    rastreio = publico.get(f'/api/public/orders/{pedido.rastreamento_token}/')
    assert rastreio.status_code == 200


def test_configuracao_do_delivery_salva_pelos_nomes_da_api(auth_client, loja_aberta):
    resposta = auth_client.patch('/api/delivery/configuracao/', {
        'aceita_pedidos': False,
        'pix_chave': 'pix@bellafornada.com',
        'pix_beneficiario': 'Bella Fornada',
    }, format='json')
    assert resposta.status_code == 200
    loja_aberta.refresh_from_db()
    assert loja_aberta.aceita_pedidos is False
    assert loja_aberta.pix_chave == 'pix@bellafornada.com'


def test_menu_publico_por_slug_funciona_em_instalacao_nova(db):
    assert not ConfiguracaoDelivery.objects.exists()
    resposta = APIClient().get('/api/public/bella-fornada/menu/')
    assert resposta.status_code == 200
