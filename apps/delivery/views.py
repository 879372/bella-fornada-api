import hashlib
import json

from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import filters, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.produtos.models import Produto

from .models import (
    BairroEntrega,
    Complemento,
    ConfiguracaoDelivery,
    Entregador,
    GrupoComplemento,
    HistoricoPedido,
    PedidoDelivery,
    ProdutoGrupoComplemento,
)
from .serializers import (
    BairroEntregaSerializer,
    ComplementoSerializer,
    ConfiguracaoDeliverySerializer,
    CriarPedidoDeliverySerializer,
    EntregadorSerializer,
    GrupoComplementoSerializer,
    PedidoDeliverySerializer,
    ProdutoGrupoComplementoSerializer,
)
from .services import alterar_status, confirmar_pagamento


def _configuracao_por_slug(slug=None):
    if slug:
        # Garante a configuração padrão numa instalação nova antes de buscar pelo slug.
        ConfiguracaoDelivery.atual()
        return get_object_or_404(ConfiguracaoDelivery, slug=slug)
    return ConfiguracaoDelivery.atual()


def _pedido_completo(pk):
    return (
        PedidoDelivery.objects.select_related("bairro", "entregador", "venda")
        .prefetch_related("itens__complementos", "historico__alterado_por")
        .get(pk=pk)
    )


def _dados_produto_cardapio(produto):
    grupos = []
    for vinculo in getattr(produto, "vinculos_delivery", []):
        complementos = list(getattr(vinculo.grupo, "complementos_delivery_ativos", []))
        if len(complementos) < vinculo.minimo_escolhas:
            return None
        if complementos:
            grupos.append(
                {
                    "id": vinculo.grupo_id,
                    "nome": vinculo.grupo.nome,
                    "descricao": vinculo.grupo.descricao,
                    "minimo_escolhas": vinculo.minimo_escolhas,
                    "maximo_escolhas": min(vinculo.maximo_escolhas, len(complementos)),
                    "complementos": [
                        {
                            "id": complemento.id,
                            "nome": complemento.nome,
                            "preco_adicional": f"{complemento.preco_adicional:.2f}",
                        }
                        for complemento in complementos
                    ],
                }
            )
    return {
        "id": produto.id,
        "nome": produto.nome,
        "descricao": produto.descricao_delivery,
        "preco": f"{produto.preco_venda:.2f}",
        "unidade_medida": produto.unidade_medida,
        "imagem_url": produto.imagem_url,
        "tempo_preparo_minutos": produto.tempo_preparo_minutos,
        "grupos_complementos": grupos,
    }


class PublicMenuView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, slug=None):
        configuracao = _configuracao_por_slug(slug)
        complementos = Prefetch(
            "grupo__complementos",
            queryset=Complemento.objects.filter(ativo=True).order_by("ordem", "nome"),
            to_attr="complementos_delivery_ativos",
        )
        vinculos = Prefetch(
            "grupos_complementos_delivery",
            queryset=(
                ProdutoGrupoComplemento.objects.filter(grupo__ativo=True)
                .select_related("grupo")
                .prefetch_related(complementos)
                .order_by("ordem", "id")
            ),
            to_attr="vinculos_delivery",
        )
        produtos = (
            Produto.objects.filter(ativo=True, disponivel_delivery=True)
            .prefetch_related(vinculos)
            .order_by("grupo", "nome")
        )

        categorias = {}
        for produto in produtos:
            dados = _dados_produto_cardapio(produto)
            if not dados:
                continue
            nome_categoria = produto.grupo or "Outros"
            categoria = categorias.setdefault(
                nome_categoria,
                {
                    "id": slugify(nome_categoria) or "outros",
                    "nome": nome_categoria,
                    "produtos": [],
                },
            )
            categoria["produtos"].append(dados)

        bairros = BairroEntregaSerializer(
            BairroEntrega.objects.filter(ativo=True), many=True
        ).data
        return Response(
            {
                "loja": {
                    "nome": configuracao.nome_loja,
                    "slug": configuracao.slug,
                },
                "configuracao": ConfiguracaoDeliverySerializer(
                    configuracao, context={"request": request}
                ).data,
                "categorias": list(categorias.values()),
                "bairros": bairros,
            }
        )


class PublicOrderCreateView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, slug=None):
        configuracao = _configuracao_por_slug(slug)
        chave = request.headers.get("Idempotency-Key") or request.data.get(
            "idempotency_key"
        )
        chave = str(chave or "").strip()
        if not chave:
            return Response(
                {"idempotency_key": "Envie o cabeçalho Idempotency-Key."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(chave) > 120:
            return Response(
                {"idempotency_key": "A chave deve ter no máximo 120 caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dados = request.data.copy()
        dados.pop("idempotency_key", None)
        serializado = json.dumps(dados, sort_keys=True, default=str, ensure_ascii=False)
        fingerprint = hashlib.sha256(serializado.encode("utf-8")).hexdigest()
        existente = PedidoDelivery.objects.filter(idempotency_key=chave).first()
        if existente:
            if existente.request_fingerprint != fingerprint:
                return Response(
                    {
                        "idempotency_key": (
                            "Esta chave já foi usada com um pedido diferente."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            existente = _pedido_completo(existente.pk)
            resposta = PedidoDeliverySerializer(
                existente, context={"request": request}
            ).data
            resposta["idempotent_replay"] = True
            return Response(resposta)

        serializer = CriarPedidoDeliverySerializer(
            data=dados,
            context={
                "request": request,
                "configuracao": configuracao,
                "idempotency_key": chave,
                "request_fingerprint": fingerprint,
            },
        )
        serializer.is_valid(raise_exception=True)
        try:
            pedido = serializer.save()
        except IntegrityError:
            # Duas requisições iguais podem passar pela consulta inicial juntas;
            # a constraint única e esta releitura tornam a operação idempotente.
            existente = PedidoDelivery.objects.filter(idempotency_key=chave).first()
            if not existente or existente.request_fingerprint != fingerprint:
                raise
            pedido = existente
        pedido = _pedido_completo(pedido.pk)
        return Response(
            PedidoDeliverySerializer(pedido, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class PublicOrderTrackingView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, token):
        pedido = get_object_or_404(
            PedidoDelivery.objects.select_related("bairro", "entregador", "venda")
            .prefetch_related("itens__complementos", "historico__alterado_por"),
            rastreamento_token=token,
        )
        return Response(
            PedidoDeliverySerializer(pedido, context={"request": request}).data
        )


class ConfiguracaoDeliveryView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        return Response(
            ConfiguracaoDeliverySerializer(
                ConfiguracaoDelivery.atual(), context={"request": request}
            ).data
        )

    def patch(self, request):
        serializer = ConfiguracaoDeliverySerializer(
            ConfiguracaoDelivery.atual(),
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class BairroEntregaViewSet(viewsets.ModelViewSet):
    queryset = BairroEntrega.objects.all()
    serializer_class = BairroEntregaSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("nome",)
    ordering_fields = ("nome", "ordem", "taxa_entrega")
    http_method_names = ("get", "post", "patch", "delete", "head", "options")


class GrupoComplementoViewSet(viewsets.ModelViewSet):
    queryset = GrupoComplemento.objects.prefetch_related("complementos")
    serializer_class = GrupoComplementoSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("nome",)
    ordering_fields = ("nome", "ordem")
    http_method_names = ("get", "post", "patch", "delete", "head", "options")


class ComplementoViewSet(viewsets.ModelViewSet):
    queryset = Complemento.objects.select_related("grupo")
    serializer_class = ComplementoSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("nome", "grupo__nome")
    ordering_fields = ("nome", "ordem", "preco_adicional")
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_queryset(self):
        queryset = super().get_queryset()
        grupo = self.request.query_params.get("grupo")
        return queryset.filter(grupo_id=grupo) if grupo else queryset


class ProdutoGrupoComplementoViewSet(viewsets.ModelViewSet):
    queryset = ProdutoGrupoComplemento.objects.select_related("produto", "grupo")
    serializer_class = ProdutoGrupoComplementoSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ("ordem", "produto__nome", "grupo__nome")
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_queryset(self):
        queryset = super().get_queryset()
        produto = self.request.query_params.get("produto")
        return queryset.filter(produto_id=produto) if produto else queryset


class EntregadorViewSet(viewsets.ModelViewSet):
    queryset = Entregador.objects.select_related("usuario")
    serializer_class = EntregadorSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("nome", "telefone")
    ordering_fields = ("nome",)
    http_method_names = ("get", "post", "patch", "delete", "head", "options")


class PedidoInternoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        PedidoDelivery.objects.select_related("bairro", "entregador", "venda")
        .prefetch_related("itens__complementos", "historico__alterado_por")
        .all()
    )
    serializer_class = PedidoDeliverySerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ("created_at", "total", "status")
    ordering = ("-created_at",)

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get("status")
        fulfillment = self.request.query_params.get("fulfillment")
        busca = self.request.query_params.get("search")
        if status_param:
            queryset = queryset.filter(status=status_param)
        if fulfillment:
            queryset = queryset.filter(fulfillment=fulfillment)
        if self.request.query_params.get("ativos") == "true":
            queryset = queryset.exclude(
                status__in=(
                    PedidoDelivery.Status.CONCLUIDO,
                    PedidoDelivery.Status.CANCELADO,
                )
            )
        if busca:
            queryset = queryset.filter(
                Q(nome_cliente__icontains=busca)
                | Q(telefone_cliente__icontains=busca)
            )
        return queryset

    def _alterar_status(self, request, pedido):
        novo_status = serializers.ChoiceField(
            choices=PedidoDelivery.Status.choices
        ).run_validation(request.data.get("status"))
        if request.data.get("pagamento_confirmado") is True:
            pedido = confirmar_pagamento(
                pedido,
                request.user,
                forma_pagamento=request.data.get("payment_method"),
                troco_para=request.data.get("troco_para"),
            )
        pedido = alterar_status(
            pedido,
            novo_status,
            request.user,
            motivo_cancelamento=request.data.get("motivo_cancelamento", ""),
        )
        return Response(
            PedidoDeliverySerializer(
                _pedido_completo(pedido.pk), context={"request": request}
            ).data
        )

    @action(detail=True, methods=("post",), url_path="alterar-status")
    def alterar_status_action(self, request, pk=None):
        return self._alterar_status(request, self.get_object())

    @action(detail=True, methods=("post",), url_path="set-status")
    def set_status(self, request, pk=None):
        return self._alterar_status(request, self.get_object())

    def _confirmar_pagamento(self, request, pedido):
        pedido = confirmar_pagamento(
            pedido,
            request.user,
            forma_pagamento=request.data.get("payment_method"),
            troco_para=request.data.get("troco_para"),
        )
        return Response(
            PedidoDeliverySerializer(
                _pedido_completo(pedido.pk), context={"request": request}
            ).data
        )

    @action(detail=True, methods=("post",), url_path="confirmar-pagamento")
    def confirmar_pagamento_action(self, request, pk=None):
        return self._confirmar_pagamento(request, self.get_object())

    @action(detail=True, methods=("post",), url_path="confirm-payment")
    def confirm_payment(self, request, pk=None):
        return self._confirmar_pagamento(request, self.get_object())

    @action(detail=True, methods=("post",), url_path="atribuir-entregador")
    @transaction.atomic
    def atribuir_entregador(self, request, pk=None):
        entregador = serializers.PrimaryKeyRelatedField(
            queryset=Entregador.objects.filter(ativo=True), allow_null=True
        ).run_validation(request.data.get("entregador"))
        pedido = PedidoDelivery.objects.select_for_update().get(
            pk=self.get_object().pk
        )
        if pedido.fulfillment != PedidoDelivery.TipoAtendimento.ENTREGA and entregador:
            raise serializers.ValidationError(
                {"entregador": "Pedidos para retirada não recebem entregador."}
            )
        if pedido.status in (
            PedidoDelivery.Status.CONCLUIDO,
            PedidoDelivery.Status.CANCELADO,
        ):
            raise serializers.ValidationError(
                {"entregador": "Não é possível alterar um pedido encerrado."}
            )
        pedido.entregador = entregador
        pedido.save(update_fields=("entregador", "updated_at"))
        HistoricoPedido.objects.create(
            pedido=pedido,
            tipo=HistoricoPedido.Tipo.ATRIBUICAO,
            status_anterior=pedido.status,
            status_novo=pedido.status,
            observacao=(
                f"Entregador atribuído: {entregador.nome}."
                if entregador
                else "Atribuição de entregador removida."
            ),
            alterado_por=request.user,
        )
        return Response(
            PedidoDeliverySerializer(
                _pedido_completo(pedido.pk), context={"request": request}
            ).data
        )
