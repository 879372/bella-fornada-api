import pytest

from apps.produtos.tests.factories import ProdutoFactory


@pytest.mark.django_db
def test_por_codigo_exige_codigo_de_barras_completo(auth_client):
    produto = ProdutoFactory(codigo_barras='7891234567890', ativo=True)
    # Outro produto cujo código contém um trecho do primeiro.
    ProdutoFactory(codigo_barras='12345', ativo=True)

    response = auth_client.get('/api/produtos/por-codigo/', {'codigo': '7891234567890'})
    assert response.status_code == 200
    assert [p['id'] for p in response.data] == [produto.id]

    parcial = auth_client.get('/api/produtos/por-codigo/', {'codigo': '789123'})
    assert parcial.data == []


@pytest.mark.django_db
def test_por_codigo_usa_codigo_interno_quando_nao_ha_codigo_de_barras(auth_client):
    produto = ProdutoFactory(codigo_legado=38, codigo_barras='7890000000038', ativo=True)
    ProdutoFactory(codigo_legado=380, codigo_barras='0038', ativo=True)

    response = auth_client.get('/api/produtos/por-codigo/', {'codigo': '38'})
    assert [p['nome'] for p in response.data] == [produto.nome]


@pytest.mark.django_db
def test_por_codigo_ignora_inativos(auth_client):
    ProdutoFactory(codigo_barras='7891111111111', ativo=False)

    response = auth_client.get('/api/produtos/por-codigo/', {'codigo': '7891111111111'})
    assert response.data == []
