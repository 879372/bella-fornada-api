import pytest
from apps.clientes.tests.factories import ClienteFactory
from apps.clientes.models import Cliente

@pytest.mark.django_db
def test_listar_clientes_ativos(auth_client):
    """Garante que apenas clientes ativos são retornados por padrão."""
    ClienteFactory(nome="Cliente Ativo", ativo=True)
    ClienteFactory(nome="Cliente Inativo", ativo=False)

    url = "/api/clientes/"
    response = auth_client.get(url)

    assert response.status_code == 200
    # O ViewSet filtra por ativo=True no get_queryset
    assert len(response.data['results']) == 1
    assert response.data['results'][0]['nome'] == "Cliente Ativo"

@pytest.mark.django_db
def test_criar_cliente(auth_client):
    """Testa a criação de um novo cliente via API."""
    payload = {
        "nome": "Novo Cliente Teste",
        "cpf_cnpj": "12345678901",
        "email": "teste@cliente.com",
        "pessoa": "F",
        "tipo_cliente": "Consumidor",
        "ativo": True
    }

    url = "/api/clientes/"
    response = auth_client.post(url, payload, format='json')

    assert response.status_code == 201
    assert Cliente.objects.filter(nome="Novo Cliente Teste").exists()

@pytest.mark.django_db
def test_detalhe_cliente(auth_client):
    """Testa a recuperação de detalhes de um cliente existente."""
    cliente = ClienteFactory(nome="Joao Silva")

    url = f"/api/clientes/{cliente.id}/"
    response = auth_client.get(url)

    assert response.status_code == 200
    assert response.data['nome'] == "Joao Silva"
