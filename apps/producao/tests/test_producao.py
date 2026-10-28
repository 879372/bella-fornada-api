from decimal import Decimal

import pytest
from django.utils import timezone

from apps.produtos.models import EstoqueLoja
from apps.produtos.tests.factories import ProdutoFactory
from apps.producao.models import OrdemProducao, Receita, ReceitaIngrediente


@pytest.mark.django_db
def test_concluir_ordem_consume_insumo_e_entra_produto(auth_client, admin_user):
    farinha = ProdutoFactory(nome='Farinha', unidade_medida='KG')
    pao = ProdutoFactory(nome='Pão francês', unidade_medida='UN')
    EstoqueLoja.objects.create(produto=farinha, loja='Loja Principal', quantidade='10.000')
    EstoqueLoja.objects.create(produto=pao, loja='Loja Principal', quantidade='0.000')
    receita = Receita.objects.create(
        produto=pao,
        nome='Pão francês',
        rendimento='50.000',
        unidade_rendimento='UN',
    )
    ReceitaIngrediente.objects.create(
        receita=receita,
        ingrediente=farinha,
        quantidade='2.000',
        percentual_perda='10.00',
    )
    ordem = OrdemProducao.objects.create(
        receita=receita,
        quantidade_lotes='2.000',
        status=OrdemProducao.Status.EM_PRODUCAO,
        data_planejada=timezone.now(),
        iniciada_em=timezone.now(),
        criada_por=admin_user,
    )

    response = auth_client.post(f'/api/producao/ordens/{ordem.id}/concluir/', {}, format='json')

    assert response.status_code == 200
    ordem.refresh_from_db()
    assert ordem.status == OrdemProducao.Status.CONCLUIDA
    assert ordem.quantidade_produzida == Decimal('100.000')
    assert EstoqueLoja.objects.get(produto=farinha, loja='Loja Principal').quantidade == Decimal('5.600')
    assert EstoqueLoja.objects.get(produto=pao, loja='Loja Principal').quantidade == Decimal('100.000')


@pytest.mark.django_db
def test_concluir_ordem_sem_estoque_nao_movimenta_nada(auth_client, admin_user):
    insumo = ProdutoFactory(nome='Manteiga')
    produto = ProdutoFactory(nome='Croissant')
    EstoqueLoja.objects.create(produto=insumo, loja='Loja Principal', quantidade='1.000')
    EstoqueLoja.objects.create(produto=produto, loja='Loja Principal', quantidade='0.000')
    receita = Receita.objects.create(
        produto=produto,
        nome='Croissant',
        rendimento='12.000',
    )
    ReceitaIngrediente.objects.create(
        receita=receita,
        ingrediente=insumo,
        quantidade='2.000',
    )
    ordem = OrdemProducao.objects.create(
        receita=receita,
        quantidade_lotes='1.000',
        status=OrdemProducao.Status.EM_PRODUCAO,
        data_planejada=timezone.now(),
        criada_por=admin_user,
    )

    response = auth_client.post(f'/api/producao/ordens/{ordem.id}/concluir/', {}, format='json')

    assert response.status_code == 400
    ordem.refresh_from_db()
    assert ordem.status == OrdemProducao.Status.EM_PRODUCAO
    assert EstoqueLoja.objects.get(produto=insumo, loja='Loja Principal').quantidade == Decimal('1.000')
    assert EstoqueLoja.objects.get(produto=produto, loja='Loja Principal').quantidade == Decimal('0.000')


@pytest.mark.django_db
def test_registrar_perda_baixa_estoque(auth_client):
    produto = ProdutoFactory(nome='Bolo de milho')
    EstoqueLoja.objects.create(produto=produto, loja='Loja Principal', quantidade='8.000')

    response = auth_client.post('/api/producao/perdas/', {
        'produto': produto.id,
        'quantidade': '2.000',
        'motivo': 'SOBRA',
        'observacoes': 'Fim do dia',
    }, format='json')

    assert response.status_code == 201
    assert EstoqueLoja.objects.get(produto=produto, loja='Loja Principal').quantidade == Decimal('6.000')

