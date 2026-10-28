from rest_framework import viewsets, filters
from .models import NotaCompra
from .serializers import NotaCompraSerializer, NotaCompraReadSerializer


class NotaCompraViewSet(viewsets.ModelViewSet):
    queryset = NotaCompra.objects.all().prefetch_related('itens__produto')
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['numero_documento', 'fornecedor', 'cnpj_fornecedor']
    ordering_fields = ['data_entrada', 'valor_total']

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get('status')
        data_inicio = self.request.query_params.get('data_inicio')
        data_fim = self.request.query_params.get('data_fim')

        if status_param:
            queryset = queryset.filter(status=status_param)
        if data_inicio:
            queryset = queryset.filter(data_entrada__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(data_entrada__lte=data_fim)

        return queryset.order_by('-data_entrada')

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return NotaCompraReadSerializer
        return NotaCompraSerializer
