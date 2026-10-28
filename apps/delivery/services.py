from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.produtos.services import registrar_movimentacao
from apps.vendas.models import SessaoCaixa, Venda, VendaItem, VendaPagamento

from .models import HistoricoPedido, PedidoDelivery


TRANSICOES = {
    PedidoDelivery.Status.RECEBIDO: {
        PedidoDelivery.Status.CONFIRMADO,
        PedidoDelivery.Status.CANCELADO,
    },
    PedidoDelivery.Status.AGUARDANDO_PAGAMENTO: {
        PedidoDelivery.Status.CONFIRMADO,
        PedidoDelivery.Status.CANCELADO,
    },
    PedidoDelivery.Status.CONFIRMADO: {
        PedidoDelivery.Status.EM_PREPARO,
        PedidoDelivery.Status.CANCELADO,
    },
    PedidoDelivery.Status.EM_PREPARO: {
        PedidoDelivery.Status.PRONTO,
        PedidoDelivery.Status.CANCELADO,
    },
    PedidoDelivery.Status.PRONTO: {
        PedidoDelivery.Status.SAIU_ENTREGA,
        PedidoDelivery.Status.CONCLUIDO,
        PedidoDelivery.Status.CANCELADO,
    },
    PedidoDelivery.Status.SAIU_ENTREGA: {
        PedidoDelivery.Status.CONCLUIDO,
        PedidoDelivery.Status.CANCELADO,
    },
}


def _sessao_caixa_aberta(pedido, usuario):
    sessoes = SessaoCaixa.objects.select_for_update().filter(status="ABERTA")
    sessao_usuario = sessoes.filter(operador=usuario).order_by("-data_abertura").first()
    if sessao_usuario:
        return sessao_usuario

    if pedido.confirmado_por_id:
        sessao_confirmacao = sessoes.filter(
            operador_id=pedido.confirmado_por_id
        ).order_by("-data_abertura").first()
        if sessao_confirmacao:
            return sessao_confirmacao

    unicas = list(sessoes.order_by("-data_abertura")[:2])
    if len(unicas) == 1:
        return unicas[0]
    if not unicas:
        raise ValidationError(
            {"caixa": "Abra uma sessão de caixa antes de concluir o pedido."}
        )
    raise ValidationError(
        {
            "caixa": (
                "Há mais de uma sessão de caixa aberta. Conclua o pedido com o "
                "operador responsável por uma delas."
            )
        }
    )


def _forma_pagamento_venda(forma_delivery):
    return {
        PedidoDelivery.FormaPagamento.PIX: "PIX",
        PedidoDelivery.FormaPagamento.DINHEIRO: "DINHEIRO",
        PedidoDelivery.FormaPagamento.CARTAO: "CARTAO_CREDITO",
    }[forma_delivery]


@transaction.atomic
def confirmar_pagamento(
    pedido,
    usuario,
    forma_pagamento=None,
    troco_para=None,
):
    pedido = PedidoDelivery.objects.select_for_update().get(pk=pedido.pk)
    if pedido.status == PedidoDelivery.Status.CANCELADO:
        raise ValidationError({"pagamento": "Um pedido cancelado não pode ser pago."})
    if pedido.pagamento_confirmado:
        return pedido

    if forma_pagamento:
        formas = set(PedidoDelivery.FormaPagamento.values)
        if forma_pagamento not in formas:
            raise ValidationError({"payment_method": "Forma de pagamento inválida."})
        pedido.payment_method = forma_pagamento

    if pedido.payment_method == PedidoDelivery.FormaPagamento.DINHEIRO:
        if troco_para not in (None, ""):
            try:
                valor_troco = Decimal(str(troco_para)).quantize(Decimal("0.01"))
            except (TypeError, ValueError, ArithmeticError) as exc:
                raise ValidationError({"troco_para": "Informe um valor válido."}) from exc
            if valor_troco < pedido.total:
                raise ValidationError(
                    {"troco_para": "O valor para troco deve ser igual ou maior que o total."}
                )
            pedido.troco_para = valor_troco if valor_troco > pedido.total else None
    else:
        pedido.troco_para = None

    anterior = pedido.status
    if pedido.status == PedidoDelivery.Status.AGUARDANDO_PAGAMENTO:
        pedido.status = PedidoDelivery.Status.CONFIRMADO
        pedido.confirmado_por = usuario
    pedido.pagamento_confirmado = True
    pedido.pagamento_confirmado_em = timezone.now()
    pedido.save(
        update_fields=(
            "payment_method",
            "troco_para",
            "status",
            "confirmado_por",
            "pagamento_confirmado",
            "pagamento_confirmado_em",
            "updated_at",
        )
    )
    HistoricoPedido.objects.create(
        pedido=pedido,
        tipo=HistoricoPedido.Tipo.PAGAMENTO,
        status_anterior=anterior,
        status_novo=pedido.status,
        observacao=f"Pagamento confirmado ({pedido.get_payment_method_display()}).",
        alterado_por=usuario,
    )
    return pedido


@transaction.atomic
def concluir_pedido(pedido, usuario):
    pedido = (
        PedidoDelivery.objects.select_for_update()
        .select_related("venda", "confirmado_por")
        .prefetch_related("itens__produto")
        .get(pk=pedido.pk)
    )
    if pedido.venda_id:
        return pedido
    if not pedido.pagamento_confirmado:
        raise ValidationError(
            {"pagamento_confirmado": "Confirme o recebimento do pagamento antes de concluir."}
        )

    sessao = _sessao_caixa_aberta(pedido, usuario)
    observacoes = (
        f"Pedido delivery #{pedido.pk}. "
        f"Atendimento: {pedido.get_fulfillment_display()}. "
        f"Taxa de entrega: R$ {pedido.taxa_entrega:.2f}."
    )
    venda = Venda.objects.create(
        sessao=sessao,
        total=0,
        status="EM_ABERTO",
        observacoes=observacoes,
    )
    for item in pedido.itens.all():
        VendaItem.objects.create(
            venda=venda,
            produto=item.produto,
            quantidade=item.quantidade,
            preco_unitario=item.preco_unitario,
            subtotal=item.subtotal,
        )
        registrar_movimentacao(
            produto_id=item.produto_id,
            quantidade=item.quantidade,
            tipo="SAIDA",
            motivo="VENDA",
            loja=pedido_configuracao_loja(),
            observacoes=f"Pedido delivery #{pedido.pk} / Venda #{venda.pk}",
        )

    VendaPagamento.objects.create(
        venda=venda,
        forma=_forma_pagamento_venda(pedido.payment_method),
        valor=pedido.total,
    )
    venda.total = pedido.total
    venda.status = "FINALIZADA"
    venda.save(update_fields=("total", "status", "updated_at"))

    anterior = pedido.status
    pedido.venda = venda
    pedido.status = PedidoDelivery.Status.CONCLUIDO
    pedido.concluido_em = timezone.now()
    pedido.save(update_fields=("venda", "status", "concluido_em", "updated_at"))
    HistoricoPedido.objects.create(
        pedido=pedido,
        tipo=HistoricoPedido.Tipo.STATUS,
        status_anterior=anterior,
        status_novo=pedido.status,
        observacao=f"Pedido integrado à venda #{venda.pk}.",
        alterado_por=usuario,
    )
    return pedido


def pedido_configuracao_loja():
    # Import local evita ciclo entre serializers/configuração e o serviço de conclusão.
    from .models import ConfiguracaoDelivery

    return ConfiguracaoDelivery.atual().loja_estoque


@transaction.atomic
def alterar_status(pedido, novo_status, usuario, motivo_cancelamento=""):
    pedido = PedidoDelivery.objects.select_for_update().get(pk=pedido.pk)
    if (
        pedido.status == PedidoDelivery.Status.CONCLUIDO
        and novo_status == PedidoDelivery.Status.CONCLUIDO
        and pedido.venda_id
    ):
        return pedido

    permitidos = TRANSICOES.get(pedido.status, set())
    if novo_status not in permitidos:
        raise ValidationError({"status": "Transição de status não permitida."})

    if (
        pedido.fulfillment == PedidoDelivery.TipoAtendimento.RETIRADA
        and novo_status == PedidoDelivery.Status.SAIU_ENTREGA
    ):
        raise ValidationError({"status": "Pedidos para retirada não saem para entrega."})
    if (
        pedido.fulfillment == PedidoDelivery.TipoAtendimento.ENTREGA
        and pedido.status == PedidoDelivery.Status.PRONTO
        and novo_status == PedidoDelivery.Status.CONCLUIDO
    ):
        raise ValidationError(
            {"status": "Marque o pedido como saiu para entrega antes de concluir."}
        )

    if novo_status == PedidoDelivery.Status.CONCLUIDO:
        return concluir_pedido(pedido, usuario)

    anterior = pedido.status
    if novo_status == PedidoDelivery.Status.CANCELADO:
        motivo = (motivo_cancelamento or "").strip()
        if not motivo:
            raise ValidationError(
                {"motivo_cancelamento": "Informe o motivo do cancelamento."}
            )
        pedido.motivo_cancelamento = motivo
        pedido.cancelado_em = timezone.now()
    if novo_status == PedidoDelivery.Status.CONFIRMADO:
        pedido.confirmado_por = usuario
    pedido.status = novo_status
    pedido.save(
        update_fields=(
            "status",
            "confirmado_por",
            "motivo_cancelamento",
            "cancelado_em",
            "updated_at",
        )
    )
    HistoricoPedido.objects.create(
        pedido=pedido,
        tipo=HistoricoPedido.Tipo.STATUS,
        status_anterior=anterior,
        status_novo=novo_status,
        observacao=pedido.motivo_cancelamento if novo_status == PedidoDelivery.Status.CANCELADO else "",
        alterado_por=usuario,
    )
    return pedido
