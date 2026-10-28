from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.produtos.models import EstoqueLoja
from apps.produtos.services import registrar_movimentacao

from .models import OrdemProducao, PerdaProducao


@transaction.atomic
def iniciar_ordem(ordem_id, usuario):
    ordem = OrdemProducao.objects.select_for_update().select_related('receita').get(
        pk=ordem_id
    )
    if ordem.status != OrdemProducao.Status.PLANEJADA:
        raise ValidationError('Apenas ordens planejadas podem ser iniciadas.')
    if not ordem.receita.ativa:
        raise ValidationError('A ficha técnica está inativa.')
    ordem.status = OrdemProducao.Status.EM_PRODUCAO
    ordem.iniciada_em = timezone.now()
    ordem.save(update_fields=('status', 'iniciada_em', 'updated_at'))
    return ordem


@transaction.atomic
def concluir_ordem(ordem_id, usuario, quantidade_produzida=None):
    ordem = (
        OrdemProducao.objects.select_for_update()
        .select_related('receita__produto')
        .get(pk=ordem_id)
    )
    if ordem.status != OrdemProducao.Status.EM_PRODUCAO:
        raise ValidationError('A ordem precisa estar em produção para ser concluída.')

    ingredientes = list(
        ordem.receita.ingredientes.select_related('ingrediente').filter(is_deleted=False)
    )
    if not ingredientes:
        raise ValidationError('A ficha técnica não possui ingredientes.')

    consumos = []
    for item in ingredientes:
        quantidade = (item.quantidade_com_perda * ordem.quantidade_lotes).quantize(
            Decimal('0.001')
        )
        estoque = (
            EstoqueLoja.objects.select_for_update()
            .filter(produto=item.ingrediente, loja='Loja Principal')
            .first()
        )
        saldo = estoque.quantidade if estoque else Decimal('0')
        if saldo < quantidade:
            raise ValidationError(
                f'Estoque insuficiente de {item.ingrediente.nome}: '
                f'disponível {saldo}, necessário {quantidade}.'
            )
        consumos.append((item.ingrediente_id, quantidade))

    for produto_id, quantidade in consumos:
        registrar_movimentacao(
            produto_id=produto_id,
            quantidade=quantidade,
            tipo='SAIDA',
            motivo='PRODUCAO',
            loja='Loja Principal',
            observacoes=f'Consumo da ordem de produção #{ordem.id}',
        )

    produzida = Decimal(str(quantidade_produzida or ordem.quantidade_prevista)).quantize(
        Decimal('0.001')
    )
    if produzida <= 0:
        raise ValidationError('A quantidade produzida deve ser maior que zero.')

    registrar_movimentacao(
        produto_id=ordem.receita.produto_id,
        quantidade=produzida,
        tipo='ENTRADA',
        motivo='PRODUCAO',
        loja='Loja Principal',
        observacoes=f'Produção concluída — ordem #{ordem.id}',
    )

    ordem.status = OrdemProducao.Status.CONCLUIDA
    ordem.quantidade_produzida = produzida
    ordem.concluida_em = timezone.now()
    ordem.concluida_por = usuario
    ordem.save(update_fields=(
        'status', 'quantidade_produzida', 'concluida_em',
        'concluida_por', 'updated_at',
    ))
    return ordem


@transaction.atomic
def cancelar_ordem(ordem_id):
    ordem = OrdemProducao.objects.select_for_update().get(pk=ordem_id)
    if ordem.status not in (
        OrdemProducao.Status.PLANEJADA,
        OrdemProducao.Status.EM_PRODUCAO,
    ):
        raise ValidationError('Esta ordem não pode mais ser cancelada.')
    ordem.status = OrdemProducao.Status.CANCELADA
    ordem.save(update_fields=('status', 'updated_at'))
    return ordem


@transaction.atomic
def registrar_perda(*, produto, quantidade, motivo, observacoes, usuario):
    perda = PerdaProducao.objects.create(
        produto=produto,
        quantidade=quantidade,
        motivo=motivo,
        observacoes=observacoes,
        registrada_por=usuario,
    )
    registrar_movimentacao(
        produto_id=produto.id,
        quantidade=quantidade,
        tipo='SAIDA',
        motivo='QUEBRA',
        loja='Loja Principal',
        observacoes=f'{perda.get_motivo_display()}: {observacoes}'.strip(': '),
    )
    return perda

