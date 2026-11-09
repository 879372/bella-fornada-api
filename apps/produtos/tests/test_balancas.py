from decimal import Decimal

import pytest

from apps.produtos.tests.factories import ProdutoFactory


@pytest.mark.django_db
def test_salva_configuracao_da_balanca(auth_client):
    response = auth_client.patch(
        '/api/balancas/configuracao/',
        {
            'modelo': 'Prix 4 Uno',
            'versao_mgv': 'MGV 6',
            'ip': '192.168.1.150',
            'porta': 0,
            'departamento': 1,
            'validade_padrao_dias': 2,
            'prefixo_ean': '2',
        },
        format='json',
    )

    assert response.status_code == 200
    assert response.data['ip'] == '192.168.1.150'
    assert response.data['modelo'] == 'Prix 4 Uno'


@pytest.mark.django_db
def test_exporta_somente_produtos_ativos_vendidos_por_kg(auth_client):
    ProdutoFactory(
        codigo_legado=149,
        nome='PAO DE QUEIJO MINEIRO',
        preco_venda=Decimal('39.99'),
        unidade_medida='KG',
        ativo=True,
    )
    ProdutoFactory(unidade_medida='UN', ativo=True)
    ProdutoFactory(unidade_medida='KG', ativo=False)

    response = auth_client.get('/api/balancas/exportar/')
    conteudo = response.content.decode('utf-8-sig')

    assert response.status_code == 200
    assert 'PLU;DESCRICAO;PRECO_KG;VALIDADE_DIAS;DEPARTAMENTO;TIPO' in conteudo
    assert '149;PAO DE QUEIJO MINEIRO;39,99;1;1;PESO' in conteudo
    assert conteudo.count('\n') == 2
