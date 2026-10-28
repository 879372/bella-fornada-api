from django.db import models
from apps.core.models import BaseModel, ActiveManager


class CategoriaFinanceira(BaseModel):
    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=[('PAGAR', 'Pagar'), ('RECEBER', 'Receber')])

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'financeiro'

    def __str__(self):
        return self.nome


class ContaPagar(BaseModel):
    STATUS_CHOICES = [('PENDENTE', 'Pendente'), ('PAGO', 'Pago'), ('VENCIDO', 'Vencido')]
    descricao = models.CharField(max_length=255)
    fornecedor = models.CharField(max_length=255, blank=True)
    categoria = models.ForeignKey(CategoriaFinanceira, null=True, blank=True, on_delete=models.SET_NULL)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    vencimento = models.DateField()
    data_pagamento = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDENTE')
    observacoes = models.TextField(blank=True)

    # Recorrência
    recorrente = models.BooleanField(default=False)
    data_fim_recorrencia = models.DateField(null=True, blank=True)
    proxima_recorrencia = models.DateField(null=True, blank=True, help_text="Usado internamente para controle")
    parcela_atual = models.IntegerField(default=1)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'financeiro'

    def __str__(self):
        return f"{self.descricao} - R$ {self.valor} ({self.status})"


class ContaReceber(BaseModel):
    STATUS_CHOICES = [('PENDENTE', 'Pendente'), ('RECEBIDO', 'Recebido'), ('VENCIDO', 'Vencido')]
    descricao = models.CharField(max_length=255)
    cliente_nome = models.CharField(max_length=255, blank=True)
    categoria = models.ForeignKey(CategoriaFinanceira, null=True, blank=True, on_delete=models.SET_NULL)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    vencimento = models.DateField()
    data_recebimento = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDENTE')
    observacoes = models.TextField(blank=True)

    # Recorrência
    recorrente = models.BooleanField(default=False)
    data_fim_recorrencia = models.DateField(null=True, blank=True)
    proxima_recorrencia = models.DateField(null=True, blank=True, help_text="Usado internamente para controle")
    parcela_atual = models.IntegerField(default=1)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'financeiro'

    def __str__(self):
        return f"{self.descricao} - R$ {self.valor} ({self.status})"
