from decimal import Decimal
from django.db import IntegrityError, transaction
from .models import EstoqueLoja, MovimentacaoEstoque

def registrar_movimentacao(produto_id, quantidade, tipo, motivo, loja='Loja Principal', observacoes=''):
    """
    Registra uma movimentação no estoque (Kardex) e atualiza o saldo atual em EstoqueLoja.
    quantidade: valor positivo (a lógica de soma/subtração depende do 'tipo')
    """
    quantidade = Decimal(str(quantidade))
    if quantidade <= 0:
        raise ValueError('A quantidade da movimentação deve ser maior que zero.')
    if tipo not in dict(MovimentacaoEstoque.TIPO_CHOICES):
        raise ValueError('Tipo de movimentação inválido.')

    with transaction.atomic():
        # 1. Busca ou cria o registro de estoque na loja
        estoque = EstoqueLoja.objects.select_for_update().filter(
            produto_id=produto_id, loja=loja
        ).first()
        if estoque is None:
            try:
                with transaction.atomic():
                    EstoqueLoja.objects.create(
                        produto_id=produto_id, loja=loja, quantidade=0
                    )
            except IntegrityError:
                # Outro processo pode ter criado o saldo entre o SELECT e o INSERT.
                pass
            estoque = EstoqueLoja.objects.select_for_update().get(
                produto_id=produto_id, loja=loja
            )

        saldo_anterior = estoque.quantidade

        # 2. Calcula novo saldo
        if tipo == 'ENTRADA':
            estoque.quantidade += quantidade
        else:
            if estoque.quantidade < quantidade:
                # Opcional: Levantar erro se estoque ficar negativo,
                # mas para hortifruti as vezes permite-se vender sem estoque e ajustar depois
                pass
            estoque.quantidade -= quantidade

        estoque.save()

        # 3. Cria o registro no Kardex
        mov = MovimentacaoEstoque.objects.create(
            produto_id=produto_id,
            tipo=tipo,
            motivo=motivo,
            quantidade=quantidade,
            saldo_anterior=saldo_anterior,
            saldo_atual=estoque.quantidade,
            observacoes=observacoes
        )

        return mov
