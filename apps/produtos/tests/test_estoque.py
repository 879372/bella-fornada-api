import pytest
from decimal import Decimal
from apps.produtos.tests.factories import ProdutoFactory, EstoqueLojaFactory
from apps.produtos.services import registrar_movimentacao
from apps.produtos.models import MovimentacaoEstoque

@pytest.mark.django_db
def test_registrar_entrada_estoque():
    """Valida se uma entrada de estoque aumenta o saldo e gera log."""
    produto = ProdutoFactory()
    estoque = EstoqueLojaFactory(produto=produto, quantidade=Decimal("10.00"), loja="Matriz")

    registrar_movimentacao(
        produto_id=produto.id,
        quantidade=Decimal("5.00"),
        tipo='ENTRADA',
        motivo='COMPRA',
        loja='Matriz'
    )

    estoque.refresh_from_db()
    assert estoque.quantidade == Decimal("15.00")

    log = MovimentacaoEstoque.objects.filter(produto=produto, tipo='ENTRADA').first()
    assert log.quantidade == Decimal("5.00")
    assert log.saldo_atual == Decimal("15.00")

@pytest.mark.django_db
def test_registrar_saida_estoque():
    """Valida se uma saída de estoque diminui o saldo."""
    produto = ProdutoFactory()
    estoque = EstoqueLojaFactory(produto=produto, quantidade=Decimal("10.00"), loja="Matriz")

    registrar_movimentacao(
        produto_id=produto.id,
        quantidade=Decimal("3.00"),
        tipo='SAIDA',
        motivo='AJUSTE',
        loja='Matriz'
    )

    estoque.refresh_from_db()
    assert estoque.quantidade == Decimal("7.00")

@pytest.mark.django_db
def test_estoque_negativo_permitido():
    """Valida se o sistema permite estoque negativo (comum em hortifruti)."""
    produto = ProdutoFactory()
    estoque = EstoqueLojaFactory(produto=produto, quantidade=Decimal("1.00"), loja="Matriz")

    registrar_movimentacao(
        produto_id=produto.id,
        quantidade=Decimal("5.00"),
        tipo='SAIDA',
        motivo='VENDA',
        loja='Matriz'
    )

    estoque.refresh_from_db()
    assert estoque.quantidade == Decimal("-4.00")
