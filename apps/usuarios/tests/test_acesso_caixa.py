import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.usuarios.models import PerfilUsuario
from apps.vendas.tests.factories import SessaoCaixaFactory, VendaFactory

pytestmark = pytest.mark.django_db


def cliente_com_papel(papel):
    user = User.objects.create_user(username=f'u_{papel.lower()}', password='senha-forte-123')
    PerfilUsuario.objects.update_or_create(usuario=user, defaults={'papel': papel})
    client = APIClient()
    # Token real: force_authenticate pularia a autenticação que aplica a regra.
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return client, user


@pytest.mark.parametrize('url', [
    '/api/dashboard-stats/', '/api/financeiro/contas-pagar/', '/api/usuarios/',
    '/api/sessoes-caixa/gestao/', '/api/delivery/configuracao/', '/api/balancas/configuracao/',
])
def test_caixa_nao_acessa_painel_administrativo(url):
    client, _ = cliente_com_papel('CAIXA')
    assert client.get(url).status_code == 403


def test_caixa_nao_altera_cadastros_mesmo_com_rota_de_leitura():
    client, _ = cliente_com_papel('CAIXA')
    assert client.post('/api/clientes/', {'nome': 'X'}).status_code == 403
    assert client.post('/api/produtos/', {'nome': 'X'}).status_code == 403


def test_caixa_usa_as_rotas_do_pdv():
    client, user = cliente_com_papel('CAIXA')
    assert client.get('/api/auth/me/').status_code == 200
    assert client.get('/api/sessoes-caixa/ativa/').status_code == 200
    assert client.get('/api/produtos/busca-pdv/', {'q': 'pao'}).status_code == 200
    assert client.get('/api/clientes/').status_code == 200
    assert client.get('/api/fiscal/documentos/').status_code == 200
    assert client.post('/api/sessoes-caixa/', {'fundo_inicial': '50.00'}).status_code == 201


def test_caixa_lista_somente_as_proprias_vendas_e_sessoes():
    client, user = cliente_com_papel('CAIXA')
    propria = VendaFactory(sessao=SessaoCaixaFactory(operador=user), status='EM_ABERTO')
    alheia = VendaFactory(status='EM_ABERTO')
    vendas = client.get('/api/vendas/').data['results']
    assert [v['id'] for v in vendas] == [propria.id]
    assert client.get(f'/api/vendas/{alheia.id}/').status_code == 404
    sessoes = client.get('/api/sessoes-caixa/').data['results']
    assert [s['id'] for s in sessoes] == [propria.sessao_id]


def test_gerente_continua_com_acesso_ao_painel():
    client, _ = cliente_com_papel('GERENTE')
    assert client.get('/api/dashboard-stats/').status_code == 200
    assert client.get('/api/sessoes-caixa/gestao/').status_code == 200


def test_perfil_informa_se_o_usuario_e_somente_pdv():
    caixa, _ = cliente_com_papel('CAIXA')
    gerente, _ = cliente_com_papel('GERENTE')
    assert caixa.get('/api/auth/me/').data['somente_pdv'] is True
    assert gerente.get('/api/auth/me/').data['somente_pdv'] is False


def test_staff_com_papel_caixa_nao_fica_preso_ao_pdv():
    client, user = cliente_com_papel('CAIXA')
    user.is_staff = True
    user.save()
    assert client.get('/api/dashboard-stats/').status_code == 200
