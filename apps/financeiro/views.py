from rest_framework import viewsets, filters
from .models import ContaPagar, ContaReceber, CategoriaFinanceira
from .serializers import (
    ContaPagarSerializer,
    ContaPagarReadSerializer,
    ContaReceberSerializer,
    ContaReceberReadSerializer,
    CategoriaFinanceiraSerializer
)


class CategoriaFinanceiraViewSet(viewsets.ModelViewSet):
    queryset = CategoriaFinanceira.objects.all()
    serializer_class = CategoriaFinanceiraSerializer


from django.db import transaction
from datetime import date
from dateutil.relativedelta import relativedelta

class ContaPagarViewSet(viewsets.ModelViewSet):
    queryset = ContaPagar.objects.all().select_related('categoria')
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['descricao', 'fornecedor']
    ordering_fields = ['vencimento', 'valor', 'status']

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ContaPagarReadSerializer
        return ContaPagarSerializer

    def perform_create(self, serializer):
        with transaction.atomic():
            conta = serializer.save()
            if conta.recorrente and conta.data_fim_recorrencia:
                current_venc = conta.vencimento
                parcela = 1
                while True:
                    current_venc = current_venc + relativedelta(months=1)
                    if current_venc > conta.data_fim_recorrencia:
                        break
                    parcela += 1
                    ContaPagar.objects.create(
                        descricao=f"{conta.descricao} ({parcela})",
                        fornecedor=conta.fornecedor,
                        categoria=conta.categoria,
                        valor=conta.valor,
                        vencimento=current_venc,
                        status='PENDENTE',
                        recorrente=True,
                        data_fim_recorrencia=conta.data_fim_recorrencia,
                        parcela_atual=parcela,
                    )


class ContaReceberViewSet(viewsets.ModelViewSet):
    queryset = ContaReceber.objects.all().select_related('categoria')
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['descricao', 'cliente_nome']
    ordering_fields = ['vencimento', 'valor', 'status']

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ContaReceberReadSerializer
        return ContaReceberSerializer

    def perform_create(self, serializer):
        with transaction.atomic():
            conta = serializer.save()
            if conta.recorrente and conta.data_fim_recorrencia:
                current_venc = conta.vencimento
                parcela = 1
                while True:
                    current_venc = current_venc + relativedelta(months=1)
                    if current_venc > conta.data_fim_recorrencia:
                        break
                    parcela += 1
                    ContaReceber.objects.create(
                        descricao=f"{conta.descricao} ({parcela})",
                        cliente_nome=conta.cliente_nome,
                        categoria=conta.categoria,
                        valor=conta.valor,
                        vencimento=current_venc,
                        status='PENDENTE',
                        recorrente=True,
                        data_fim_recorrencia=conta.data_fim_recorrencia,
                        parcela_atual=parcela,
                    )
