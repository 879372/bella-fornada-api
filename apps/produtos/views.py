import csv
import logging

from django.db.models import Q
from django.http import HttpResponse
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usuarios.permissions import CanChangePdvPrice, IsAdminOrManager

from .barcodes import interpretar_etiqueta_balanca
from .models import ConfiguracaoBalanca, Produto, Grupo
from .serializers import (
    AtualizarPrecoPdvSerializer,
    ConfiguracaoBalancaSerializer,
    GrupoSerializer,
    ProdutoReadSerializer,
    ProdutoSerializer,
    ProdutoSimplificadoSerializer,
)


logger = logging.getLogger(__name__)


class ConfiguracaoBalancaView(APIView):
    def get(self, request):
        return Response(ConfiguracaoBalancaSerializer(ConfiguracaoBalanca.atual()).data)

    def patch(self, request):
        configuracao = ConfiguracaoBalanca.atual()
        serializer = ConfiguracaoBalancaSerializer(
            configuracao, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ExportarCargaBalancaView(APIView):
    def get(self, request):
        configuracao = ConfiguracaoBalanca.atual()
        produtos = Produto.objects.filter(
            ativo=True, unidade_medida__iexact='KG'
        ).order_by('codigo_legado')

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="carga_balanca.csv"'
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';', lineterminator='\r\n')
        writer.writerow([
            'PLU', 'DESCRICAO', 'PRECO_KG', 'VALIDADE_DIAS',
            'DEPARTAMENTO', 'TIPO',
        ])
        for produto in produtos:
            writer.writerow([
                produto.codigo_legado,
                produto.nome[:40],
                f'{produto.preco_venda:.2f}'.replace('.', ','),
                configuracao.validade_padrao_dias,
                configuracao.departamento,
                'PESO',
            ])
        return response


class GrupoViewSet(viewsets.ModelViewSet):
    queryset = Grupo.objects.all()
    serializer_class = GrupoSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['nome']


class ProdutoViewSet(viewsets.ModelViewSet):
    queryset = Produto.objects.all().prefetch_related('estoques').order_by('codigo_legado')
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nome', 'codigo_barras', 'codigo_legado']
    ordering_fields = ['nome', 'preco_venda', 'grupo']

    def get_permissions(self):
        if self.action == 'preco_pdv':
            permission_classes = (permissions.IsAuthenticated, CanChangePdvPrice)
        elif self.action in {'create', 'update', 'partial_update', 'destroy'}:
            permission_classes = (permissions.IsAuthenticated, IsAdminOrManager)
        else:
            permission_classes = (permissions.IsAuthenticated,)
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        # Retorna todos os produtos para a gestão (ativos e inativos)
        return super().get_queryset()

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ProdutoReadSerializer
        return ProdutoSerializer

    @action(detail=False, methods=['get'], url_path='sugestao-fiscal')
    def sugestao_fiscal(self, request):
        """Pré-preenche a classificação fiscal do cadastro conforme o tipo e a família do produto."""
        from apps.fiscal.models import ConfiguracaoFiscal
        from .catalog_fiscal_rules import suggest_fiscal_fields

        params = request.query_params
        produto = Produto(
            nome=params.get('nome', '').strip(),
            grupo=params.get('grupo', '').strip(),
            codigo_barras=params.get('codigo_barras', '').strip(),
            unidade_medida=params.get('unidade_medida', '').strip() or 'UN',
        )
        campos = suggest_fiscal_fields(produto, params.get('tipo_origem_comercial') or None)
        regime = ConfiguracaoFiscal.atual().codigo_regime_tributario
        alerta = '' if regime in {'1', '4'} else (
            'A empresa não está no Simples Nacional: a sugestão usa CSOSN e precisa ser '
            'convertida para CST pelo contador.'
        )
        return Response({'campos': campos, 'alerta': alerta})

    @action(detail=False, methods=['get'], url_path='busca-pdv')
    def busca_pdv(self, request):
        """Busca rápida para o PDV por nome ou código de barras"""
        q = request.query_params.get('q', '').strip()
        if not q:
            return Response([])

        qs = Q(nome__icontains=q) | Q(codigo_barras__icontains=q)

        # codigo_legado é IntegerField — só filtrar se for um número
        try:
            codigo_int = int(q)
            qs = qs | Q(codigo_legado=codigo_int)
        except ValueError:
            pass

        produtos = Produto.objects.filter(ativo=True).filter(qs)[:20]
        serializer = ProdutoSimplificadoSerializer(produtos, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=['patch'],
        url_path='preco-pdv',
        permission_classes=[permissions.IsAuthenticated, CanChangePdvPrice],
    )
    def preco_pdv(self, request, pk=None):
        """Altera exclusivamente o preço de venda a partir do PDV."""
        produto = self.get_object()
        serializer = AtualizarPrecoPdvSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        preco_anterior = produto.preco_venda
        produto.preco_venda = serializer.validated_data['preco_venda']
        produto.save(update_fields=['preco_venda', 'updated_at'])

        logger.info(
            'Preço de produto alterado no PDV',
            extra={
                'produto_id': str(produto.pk),
                'usuario_id': request.user.pk,
                'preco_anterior': str(preco_anterior),
                'preco_novo': str(produto.preco_venda),
            },
        )
        return Response(ProdutoSimplificadoSerializer(produto).data)


    @action(detail=False, methods=['get'], url_path='por-codigo')
    def por_codigo(self, request):
        """Busca EXATA usada pelo leitor de código de barras no PDV.

        Diferente da busca-pdv (que usa icontains para listar sugestões), aqui
        o código precisa bater por completo, para que um código parcial nunca
        adicione outro produto. Prioriza o código de barras; o código interno
        (codigo_legado) só é usado quando nenhum código de barras corresponde.
        """
        codigo = request.query_params.get('codigo', '').strip()
        if not codigo:
            return Response([])

        ativos = Produto.objects.filter(ativo=True)
        produtos = list(ativos.filter(codigo_barras=codigo)[:5])
        etiqueta = None
        if not produtos:
            etiqueta = interpretar_etiqueta_balanca(codigo)
            if etiqueta:
                produtos = list(
                    ativos.filter(
                        codigo_legado=etiqueta.codigo_produto,
                        unidade_medida__iexact='KG',
                    )[:1]
                )
        if not produtos and codigo.isdigit():
            produtos = list(ativos.filter(codigo_legado=int(codigo))[:5])

        serializer = ProdutoSimplificadoSerializer(produtos, many=True)
        data = list(serializer.data)
        if etiqueta and len(data) == 1:
            data[0]['quantidade_balanca'] = format(etiqueta.quantidade_kg, 'f')
        return Response(data)

    @action(detail=True, methods=['get'])
    def movimentacoes(self, request, pk=None):
        """Retorna o histórico de movimentações (Kardex) do produto"""
        from .models import MovimentacaoEstoque
        from .serializers import MovimentacaoEstoqueSerializer

        movs = MovimentacaoEstoque.objects.filter(produto_id=pk).order_by('-created_at')[:50]
        serializer = MovimentacaoEstoqueSerializer(movs, many=True)
        return Response(serializer.data)
