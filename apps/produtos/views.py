from django.db.models import Q
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Produto, Grupo
from .serializers import (
    ProdutoSerializer,
    ProdutoReadSerializer,
    ProdutoSimplificadoSerializer,
    GrupoSerializer
)


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

    def get_queryset(self):
        # Retorna todos os produtos para a gestão (ativos e inativos)
        return super().get_queryset()

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ProdutoReadSerializer
        return ProdutoSerializer

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
        if not produtos and codigo.isdigit():
            produtos = list(ativos.filter(codigo_legado=int(codigo))[:5])

        serializer = ProdutoSimplificadoSerializer(produtos, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def movimentacoes(self, request, pk=None):
        """Retorna o histórico de movimentações (Kardex) do produto"""
        from .models import MovimentacaoEstoque
        from .serializers import MovimentacaoEstoqueSerializer

        movs = MovimentacaoEstoque.objects.filter(produto_id=pk).order_by('-created_at')[:50]
        serializer = MovimentacaoEstoqueSerializer(movs, many=True)
        return Response(serializer.data)
