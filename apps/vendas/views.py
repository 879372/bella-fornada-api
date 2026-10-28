from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from .models import SessaoCaixa, Venda, VendaItem, VendaPagamento, OperacaoCaixa
from .serializers import (
    SessaoCaixaSerializer,
    VendaSerializer,
    VendaReadSerializer,
    VendaItemSerializer,
    VendaPagamentoSerializer,
    OperacaoCaixaSerializer,
    VendaFinalizarSerializer,
)


def _assert_session_owner(sessao, user):
    if sessao.operador_id != user.id:
        raise PermissionDenied('A sessão de caixa pertence a outro operador.')


def _assert_sale_owner(venda, user):
    _assert_session_owner(venda.sessao, user)


def _positive_decimal(value, field_name='valor'):
    try:
        parsed = Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field_name: 'Informe um valor válido.'})
    if parsed <= 0:
        raise ValidationError({field_name: 'O valor deve ser maior que zero.'})
    return parsed

@extend_schema(tags=['Caixa'])
class SessaoCaixaViewSet(viewsets.ModelViewSet):
    queryset = SessaoCaixa.objects.all().select_related('operador')
    serializer_class = SessaoCaixaSerializer
    def get_queryset(self):
        queryset = super().get_queryset()
        data_inicio = self.request.query_params.get('data_inicio')
        data_fim = self.request.query_params.get('data_fim')

        if data_inicio:
            queryset = queryset.filter(data_abertura__date__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(data_abertura__date__lte=data_fim)

        return queryset.order_by('-data_abertura')

    def perform_create(self, serializer):
        serializer.save(operador=self.request.user)

    def perform_update(self, serializer):
        with transaction.atomic():
            sessao = SessaoCaixa.objects.select_for_update().get(pk=serializer.instance.pk)
            _assert_session_owner(sessao, self.request.user)
            serializer.instance = sessao
            serializer.save()

    def perform_destroy(self, instance):
        _assert_session_owner(instance, self.request.user)
        if instance.status != 'ABERTA' or instance.venda_set.exists():
            raise ValidationError('Não é possível excluir uma sessão utilizada ou fechada.')
        instance.soft_delete()

    @action(detail=False, methods=['get'], url_path='ativa')
    def sessao_ativa(self, request):
        """Retorna a sessão de caixa aberta do usuário atual, se houver."""
        sessao = SessaoCaixa.objects.filter(operador=request.user, status='ABERTA').last()
        if sessao:
            return Response(SessaoCaixaSerializer(sessao).data)
        return Response(None)

    @action(detail=True, methods=['post'], url_path='fechar')
    def fechar(self, request, pk=None):
        """Fecha a sessão de caixa e retorna o resumo financeiro."""
        from django.utils import timezone
        valor_contado = request.data.get('valor_contado')
        if valor_contado in (None, ''):
            return Response({'erro': 'Informe o valor contado no caixa.'}, status=400)
        try:
            valor_contado = Decimal(str(valor_contado)).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError, ValueError):
            return Response({'erro': 'Valor contado inválido.'}, status=400)
        if valor_contado < 0:
            return Response({'erro': 'O valor contado não pode ser negativo.'}, status=400)

        with transaction.atomic():
            sessao = SessaoCaixa.objects.select_for_update().get(pk=self.get_object().pk)
            _assert_session_owner(sessao, request.user)
            if sessao.status == 'FECHADA':
                return Response({'erro': 'Este caixa já está fechado.'}, status=400)
            if Venda.objects.filter(sessao=sessao, status='EM_ABERTO').exists():
                return Response({'erro': 'Não é possível fechar o caixa com vendas em aberto. Finalize ou cancele as vendas pendentes.'}, status=400)

            vendas = Venda.objects.filter(sessao=sessao, status='FINALIZADA')
            pagamentos = VendaPagamento.objects.filter(venda__in=vendas)
            resumo = {
                'total_vendas': vendas.aggregate(total=Sum('total'))['total'] or Decimal('0'),
                'quantidade_vendas': vendas.count(),
                'por_forma': {},
            }
            for forma, _label in VendaPagamento.FORMA_CHOICES:
                resumo['por_forma'][forma] = pagamentos.filter(forma=forma).aggregate(
                    total=Sum('valor')
                )['total'] or Decimal('0')

            total_dinheiro = resumo['por_forma'].get('DINHEIRO', Decimal('0'))
            total_sangrias = sessao.operacoes.filter(tipo='SANGRIA').aggregate(total=Sum('valor'))['total'] or Decimal('0')
            total_suprimentos = sessao.operacoes.filter(tipo='SUPRIMENTO').aggregate(total=Sum('valor'))['total'] or Decimal('0')
            valor_esperado = (sessao.fundo_inicial or Decimal('0')) + total_dinheiro + total_suprimentos - total_sangrias
            diferenca = valor_contado - valor_esperado
            resumo.update({'valor_esperado': valor_esperado, 'valor_contado': valor_contado, 'diferenca': diferenca})

            sessao.status = 'FECHADA'
            sessao.data_fechamento = timezone.now()
            sessao.valor_contado = valor_contado
            sessao.diferenca_caixa = diferenca
            sessao.save(update_fields=['status', 'data_fechamento', 'valor_contado', 'diferenca_caixa', 'updated_at'])

        return Response({
            'sessao': SessaoCaixaSerializer(sessao).data,
            'resumo': resumo
        })

    @action(detail=True, methods=['post'], url_path='sangria')
    def sangria(self, request, pk=None):
        valor = request.data.get('valor')
        motivo = request.data.get('motivo', '')

        try:
            valor = _positive_decimal(valor)
        except ValidationError:
            return Response({'erro': 'Valor inválido.'}, status=400)

        with transaction.atomic():
            sessao = SessaoCaixa.objects.select_for_update().get(pk=self.get_object().pk)
            _assert_session_owner(sessao, request.user)
            if sessao.status == 'FECHADA':
                return Response({'erro': 'Caixa fechado.'}, status=400)
            op = OperacaoCaixa.objects.create(
                sessao=sessao, tipo='SANGRIA', valor=valor, motivo=motivo
            )
        return Response(OperacaoCaixaSerializer(op).data, status=201)

    @action(detail=True, methods=['post'], url_path='suprimento')
    def suprimento(self, request, pk=None):
        valor = request.data.get('valor')
        motivo = request.data.get('motivo', '')

        try:
            valor = _positive_decimal(valor)
        except ValidationError:
            return Response({'erro': 'Valor inválido.'}, status=400)

        with transaction.atomic():
            sessao = SessaoCaixa.objects.select_for_update().get(pk=self.get_object().pk)
            _assert_session_owner(sessao, request.user)
            if sessao.status == 'FECHADA':
                return Response({'erro': 'Caixa fechado.'}, status=400)
            op = OperacaoCaixa.objects.create(
                sessao=sessao, tipo='SUPRIMENTO', valor=valor, motivo=motivo
            )
        return Response(OperacaoCaixaSerializer(op).data, status=201)


@extend_schema(tags=['Vendas'])
class VendaViewSet(viewsets.ModelViewSet):
    queryset = Venda.objects.all().select_related(
        'cliente', 'sessao', 'sessao__operador'
    ).prefetch_related(
        'itens__produto', 'pagamentos'
    )
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['data', 'total', 'status']

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'finalizar', 'cancelar']:
            return VendaReadSerializer
        return VendaSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        sessao = self.request.query_params.get('sessao')
        status = self.request.query_params.get('status')
        data_inicio = self.request.query_params.get('data_inicio')
        data_fim = self.request.query_params.get('data_fim')

        if sessao:
            queryset = queryset.filter(sessao_id=sessao)
        if status:
            queryset = queryset.filter(status=status)
        if data_inicio:
            queryset = queryset.filter(data__date__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(data__date__lte=data_fim)

        return queryset.order_by('-data')

    def perform_update(self, serializer):
        with transaction.atomic():
            venda = Venda.objects.select_for_update().select_related('sessao').get(
                pk=serializer.instance.pk
            )
            _assert_sale_owner(venda, self.request.user)
            if venda.status != 'EM_ABERTO' or venda.sessao.status != 'ABERTA':
                raise ValidationError('A venda e o caixa devem estar abertos.')
            serializer.instance = venda
            serializer.save()

    def perform_create(self, serializer):
        with transaction.atomic():
            sessao = SessaoCaixa.objects.select_for_update().get(
                pk=serializer.validated_data['sessao'].pk
            )
            _assert_session_owner(sessao, self.request.user)
            if sessao.status != 'ABERTA':
                raise ValidationError('A sessão de caixa está fechada.')
            serializer.save(sessao=sessao)

    def perform_destroy(self, instance):
        _assert_sale_owner(instance, self.request.user)
        if instance.status != 'EM_ABERTO':
            raise ValidationError('Apenas vendas em aberto podem ser excluídas.')
        instance.soft_delete()

    @extend_schema(
        summary="Finalizar uma venda",
        description="Fecha a venda, registra os pagamentos e baixa o estoque.",
        request=VendaFinalizarSerializer,
        responses={200: VendaReadSerializer}
    )
    @action(detail=True, methods=['post'], url_path='finalizar')
    def finalizar(self, request, pk=None):
        input_serializer = VendaFinalizarSerializer(data=request.data)
        if not input_serializer.is_valid():
            first_error = next(iter(input_serializer.errors.values()))
            if isinstance(first_error, list):
                first_error = first_error[0]
            return Response({'erro': str(first_error)}, status=400)

        validated = input_serializer.validated_data
        pagamentos_data = [dict(payment) for payment in validated['pagamentos']]
        desconto = validated['desconto']
        cliente = validated.get('cliente')

        with transaction.atomic():
            venda = get_object_or_404(
                # Não inclua `cliente` neste lock. A relação é opcional e, no
                # PostgreSQL, gera um LEFT OUTER JOIN no qual SELECT FOR UPDATE
                # não pode bloquear o lado anulável da junção.
                Venda.objects.select_for_update().select_related('sessao'),
                pk=pk,
            )
            _assert_sale_owner(venda, request.user)
            if venda.status != 'EM_ABERTO':
                return Response({'erro': 'Apenas vendas em aberto podem ser finalizadas.'}, status=400)
            if venda.sessao.status != 'ABERTA':
                return Response({'erro': 'A sessão de caixa está fechada.'}, status=400)

            itens = list(venda.itens.select_for_update().select_related('produto'))
            if not itens:
                return Response({'erro': 'O carrinho está vazio.'}, status=400)

            total = (
                sum((item.subtotal for item in itens), Decimal('0'))
                + (venda.taxa_entrega or Decimal('0'))
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if desconto >= total:
                return Response({
                    'erro': 'O desconto deve manter o total líquido da venda em pelo menos R$0,01.'
                }, status=400)

            total_liquido = (total - desconto).quantize(Decimal('0.01'))
            total_pago = sum((p['valor'] for p in pagamentos_data), Decimal('0')).quantize(Decimal('0.01'))
            if total_pago < total_liquido:
                return Response({
                    'erro': f'O total dos pagamentos (R${total_pago:.2f}) não atinge o total líquido da venda (R${total_liquido:.2f}).'
                }, status=400)

            troco = total_pago - total_liquido
            if troco > 0:
                pagamento_dinheiro = next((p for p in pagamentos_data if p['forma'] == 'DINHEIRO'), None)
                if not pagamento_dinheiro or troco >= pagamento_dinheiro['valor']:
                    return Response({'erro': 'Pagamento excedente só é permitido como troco em dinheiro válido.'}, status=400)
                pagamento_dinheiro['valor'] -= troco

            from apps.produtos.services import registrar_movimentacao
            for item in itens:
                registrar_movimentacao(
                    produto_id=item.produto_id,
                    quantidade=item.quantidade,
                    tipo='SAIDA',
                    motivo='VENDA',
                    loja='Loja Principal',
                    observacoes=f'Venda #{venda.id}',
                )

            for payment in pagamentos_data:
                VendaPagamento.objects.create(venda=venda, **payment)
                if payment['forma'] == 'FIADO':
                    from datetime import timedelta
                    from django.utils import timezone
                    from apps.financeiro.models import ContaReceber

                    sale_customer = cliente or venda.cliente
                    ContaReceber.objects.create(
                        descricao=f'Venda FIADO #{venda.id}',
                        cliente_nome=sale_customer.nome if sale_customer else 'Consumidor Final',
                        valor=payment['valor'],
                        vencimento=timezone.now().date() + timedelta(days=30),
                        status='PENDENTE',
                        observacoes=f'Originada da Venda #{venda.id} no PDV.',
                    )

            venda.total = total
            venda.status = 'FINALIZADA'
            venda.desconto = desconto
            if 'cliente' in validated:
                venda.cliente = cliente
            venda.save(update_fields=['total', 'status', 'desconto', 'cliente', 'updated_at'])

        return Response(VendaReadSerializer(venda).data)

    @action(detail=True, methods=['post'], url_path='cancelar')
    def cancelar(self, request, pk=None):
        motivo = str(request.data.get('motivo', '')).strip()
        if len(motivo) < 3:
            return Response(
                {'erro': 'Informe o motivo do cancelamento (mínimo de 3 caracteres).'},
                status=400,
            )

        with transaction.atomic():
            venda = get_object_or_404(
                Venda.objects.select_for_update().select_related('sessao'), pk=pk
            )
            _assert_sale_owner(venda, request.user)
            if venda.status == 'CANCELADA':
                return Response({'erro': 'Esta venda já está cancelada.'}, status=400)

            if venda.status == 'FINALIZADA':
                from apps.produtos.services import registrar_movimentacao
                for item in venda.itens.select_for_update():
                    registrar_movimentacao(
                        produto_id=item.produto_id,
                        quantidade=item.quantidade,
                        tipo='ENTRADA',
                        motivo='DEVOLUCAO',
                        loja='Loja Principal',
                        observacoes=f'Estorno Venda #{venda.id} (Cancelamento)',
                    )

                # Um FIADO ainda pendente deixa de existir junto com a venda.
                # Recebíveis já liquidados são preservados como registro financeiro.
                from apps.financeiro.models import ContaReceber
                recebiveis_pendentes = ContaReceber.objects.select_for_update().filter(
                    status='PENDENTE',
                    descricao=f'Venda FIADO #{venda.id}',
                    observacoes=f'Originada da Venda #{venda.id} no PDV.',
                )
                for recebivel in recebiveis_pendentes:
                    recebivel.soft_delete()

            from django.utils import timezone

            venda.status = 'CANCELADA'
            venda.motivo_cancelamento = motivo
            venda.cancelada_por = request.user
            venda.cancelada_em = timezone.now()
            venda.save(update_fields=[
                'status', 'motivo_cancelamento', 'cancelada_por',
                'cancelada_em', 'updated_at',
            ])

        return Response(VendaReadSerializer(venda).data)

class VendaItemViewSet(viewsets.ModelViewSet):
    queryset = VendaItem.objects.all().select_related('produto')
    serializer_class = VendaItemSerializer

    def perform_create(self, serializer):
        with transaction.atomic():
            venda = Venda.objects.select_for_update().select_related('sessao').get(
                pk=serializer.validated_data['venda'].pk
            )
            _assert_sale_owner(venda, self.request.user)
            if venda.status != 'EM_ABERTO' or venda.sessao.status != 'ABERTA':
                raise ValidationError('A venda e o caixa devem estar abertos.')

            # Mesmo produto bipado de novo: soma na linha existente em vez de
            # criar outra, mantendo o carrinho igual ao que o PDV exibe.
            produto = serializer.validated_data['produto']
            existente = (
                venda.itens.select_for_update()
                .filter(produto=produto, preco_unitario=produto.preco_venda)
                .first()
            )
            if existente:
                existente.quantidade += serializer.validated_data['quantidade']
                existente.save()
                serializer.instance = existente
                return
            serializer.save(venda=venda)

    def perform_update(self, serializer):
        with transaction.atomic():
            item = VendaItem.objects.select_for_update().select_related('venda__sessao').get(
                pk=serializer.instance.pk
            )
            _assert_sale_owner(item.venda, self.request.user)
            if item.venda.status != 'EM_ABERTO' or item.venda.sessao.status != 'ABERTA':
                raise ValidationError('A venda e o caixa devem estar abertos.')
            serializer.instance = item
            serializer.save()

    def perform_destroy(self, instance):
        with transaction.atomic():
            item = VendaItem.objects.select_for_update().select_related('venda__sessao').get(
                pk=instance.pk
            )
            _assert_sale_owner(item.venda, self.request.user)
            if item.venda.status != 'EM_ABERTO' or item.venda.sessao.status != 'ABERTA':
                raise ValidationError('A venda e o caixa devem estar abertos.')
            item.delete()


class VendaPagamentoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VendaPagamento.objects.all()
    serializer_class = VendaPagamentoSerializer

class OperacaoCaixaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OperacaoCaixa.objects.all()
    serializer_class = OperacaoCaixaSerializer

def comprovante_venda_publico(request, id_externo):
    """View pública para exibir o comprovante da venda via link compartilhado"""
    venda = get_object_or_404(Venda, id_externo=id_externo)
    return render(request, 'vendas/comprovante.html', {'venda': venda})
