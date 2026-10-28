from django.db import models
from apps.produtos.models import Produto
from apps.core.models import BaseModel, ActiveManager


class NotaCompra(BaseModel):
    STATUS_CHOICES = [('RECEBIDA', 'Registrada')]
    numero_documento = models.CharField(max_length=50, blank=True)
    fornecedor = models.CharField(max_length=255)
    cnpj_fornecedor = models.CharField(max_length=20, blank=True)
    data_emissao = models.DateField(null=True, blank=True)
    data_entrada = models.DateField(auto_now_add=True)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='RECEBIDA')
    observacoes = models.TextField(blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'compras'

    def __str__(self):
        referencia = self.numero_documento or self.id
        return f"Compra {referencia} - {self.fornecedor}"


class ItemNotaCompra(BaseModel):
    nota = models.ForeignKey(NotaCompra, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, null=True, blank=True, on_delete=models.SET_NULL)
    descricao = models.CharField(max_length=255)
    quantidade = models.DecimalField(max_digits=10, decimal_places=3)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'compras'

    def __str__(self):
        return f"{self.descricao} x {self.quantidade}"
