from rest_framework import viewsets, filters
from .models import Cliente
from .serializers import ClienteSerializer, ClienteReadSerializer


class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nome', 'razao_social', 'cpf_cnpj', 'telefone']
    ordering_fields = ['nome', 'cidade']

    def get_queryset(self):
        # Filtra ativos por padrão
        return super().get_queryset().filter(ativo=True).order_by('nome', 'id')

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ClienteReadSerializer
        return ClienteSerializer
