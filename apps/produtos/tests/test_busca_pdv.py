import pytest

from apps.produtos.barcodes import gtin_valido
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


@pytest.mark.django_db
def test_por_codigo_interpreta_etiqueta_de_balanca(auth_client):
    produto = ProdutoFactory(
        codigo_legado=149,
        codigo_barras='7770000001491',
        unidade_medida='KG',
        ativo=True,
    )

    response = auth_client.get('/api/produtos/por-codigo/', {'codigo': '2001490000844'})

    assert response.status_code == 200
    assert len(response.data) == 1
    assert str(response.data[0]['id']) == str(produto.id)
    assert response.data[0]['nome'] == produto.nome
    assert response.data[0]['quantidade_balanca'] == '0.084'


@pytest.mark.django_db
def test_por_codigo_rejeita_etiqueta_com_digito_verificador_invalido(auth_client):
    ProdutoFactory(codigo_legado=149, unidade_medida='KG', ativo=True)

    response = auth_client.get('/api/produtos/por-codigo/', {'codigo': '2001490000845'})

    assert response.data == []


def test_gtin_valido_rejeita_codigos_internos_e_aceita_gtin_comercial():
    assert gtin_valido('7896045112968') is True
    assert gtin_valido('7770000001408') is False
    assert gtin_valido('2001490000844') is False
