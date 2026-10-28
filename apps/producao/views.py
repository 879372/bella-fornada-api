from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import OrdemProducao, PerdaProducao, Receita
from .serializers import (
    ConcluirOrdemSerializer,
    OrdemProducaoSerializer,
    PerdaProducaoSerializer,
    ReceitaSerializer,
)
from .services import (
    cancelar_ordem,
    concluir_ordem,
    iniciar_ordem,
    registrar_perda,
)


class ReceitaViewSet(viewsets.ModelViewSet):
    queryset = Receita.objects.select_related('produto').prefetch_related(
        'ingredientes__ingrediente'
    )
    serializer_class = ReceitaSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ('nome', 'produto__nome')
    ordering_fields = ('nome', 'created_at')

    def perform_destroy(self, instance):
        instance.soft_delete()


class OrdemProducaoViewSet(viewsets.ModelViewSet):
    queryset = OrdemProducao.objects.select_related(
        'receita__produto', 'criada_por', 'concluida_por'
    )
    serializer_class = OrdemProducaoSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ('receita__nome', 'receita__produto__nome', 'codigo_lote')
    ordering_fields = ('data_planejada', 'created_at', 'status')

    def get_queryset(self):
        queryset = super().get_queryset()
        if status_value := self.request.query_params.get('status'):
            queryset = queryset.filter(status=status_value)
        return queryset

    def perform_create(self, serializer):
        serializer.save(criada_por=self.request.user)

    @action(detail=True, methods=('post',))
    def iniciar(self, request, pk=None):
        ordem = iniciar_ordem(pk, request.user)
        return Response(self.get_serializer(ordem).data)

    @action(detail=True, methods=('post',))
    def concluir(self, request, pk=None):
        serializer = ConcluirOrdemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ordem = concluir_ordem(
            pk,
            request.user,
            serializer.validated_data.get('quantidade_produzida'),
        )
        return Response(self.get_serializer(ordem).data)

    @action(detail=True, methods=('post',))
    def cancelar(self, request, pk=None):
        ordem = cancelar_ordem(pk)
        return Response(self.get_serializer(ordem).data)


class PerdaProducaoViewSet(viewsets.ModelViewSet):
    queryset = PerdaProducao.objects.select_related('produto', 'registrada_por')
    serializer_class = PerdaProducaoSerializer
    http_method_names = ('get', 'post', 'head', 'options')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        perda = registrar_perda(
            produto=serializer.validated_data['produto'],
            quantidade=serializer.validated_data['quantidade'],
            motivo=serializer.validated_data['motivo'],
            observacoes=serializer.validated_data.get('observacoes', ''),
            usuario=request.user,
        )
        return Response(
            self.get_serializer(perda).data,
            status=status.HTTP_201_CREATED,
        )

