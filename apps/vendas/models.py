from django.db import models
from django.contrib.auth.models import User
from apps.clientes.models import Cliente
from apps.produtos.models import Produto, EstoqueLoja
from apps.core.models import BaseModel, ActiveManager


class SessaoCaixa(BaseModel):
    STATUS_CHOICES = [('ABERTA', 'Aberta'), ('FECHADA', 'Fechada')]
    operador = models.ForeignKey(User, on_delete=models.PROTECT)
    fundo_inicial = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    data_abertura = models.DateTimeField(auto_now_add=True)
    data_fechamento = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ABERTA')
    valor_contado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    diferenca_caixa = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    observacoes = models.TextField(blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'vendas'

    def __str__(self):
        return f"Caixa {self.pk} - {self.operador.username} - {self.status}"


class Venda(BaseModel):
    STATUS_CHOICES = [
        ('EM_ABERTO', 'Em Aberto'),
        ('FINALIZADA', 'Finalizada'),
        ('CANCELADA', 'Cancelada'),
        ('ORCAMENTO', 'Orçamento'),
    ]
    CANAL_CHOICES = [
        ('BALCAO', 'Balcão / PDV'),
        ('DELIVERY', 'Delivery'),
        ('RETIRADA', 'Retirada'),
    ]
    sessao = models.ForeignKey(SessaoCaixa, on_delete=models.PROTECT)
    cliente = models.ForeignKey(Cliente, null=True, blank=True, on_delete=models.SET_NULL)
    data = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taxa_entrega = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    canal = models.CharField(max_length=12, choices=CANAL_CHOICES, default='BALCAO')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='EM_ABERTO')
    observacoes = models.TextField(blank=True)
    motivo_cancelamento = models.TextField(blank=True)
    cancelada_por = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='vendas_canceladas',
    )
    cancelada_em = models.DateTimeField(null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    @property
    def total_liquido(self):
        return (self.total or 0) - (self.desconto or 0)

    def recalcular_total(self):
        """Soma todos os itens e atualiza o total da venda"""
        from django.db.models import Sum
        novo_total = (
            self.itens.aggregate(res=Sum('subtotal'))['res'] or 0
        ) + (self.taxa_entrega or 0)
        Venda.objects.filter(pk=self.pk).update(total=novo_total)
        return novo_total

    class Meta:
        app_label = 'vendas'

    def __str__(self):
        return f"Venda #{self.pk} - R$ {self.total}"


class VendaItem(BaseModel):
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=10, decimal_places=3)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'vendas'

    def save(self, *args, **kwargs):
        self.subtotal = self.quantidade * self.preco_unitario
        super().save(*args, **kwargs)
        self.venda.recalcular_total()

    def delete(self, *args, **kwargs):
        venda = self.venda
        super().delete(*args, **kwargs)
        venda.recalcular_total()

    def __str__(self):
        return f"{self.produto.nome} x {self.quantidade}"


class VendaPagamento(BaseModel):
    FORMA_CHOICES = [
        ('DINHEIRO', 'Dinheiro'),
        ('CARTAO_DEBITO', 'Cartão Débito'),
        ('CARTAO_CREDITO', 'Cartão Crédito'),
        ('PIX', 'Pix'),
        ('FIADO', 'Fiado'),
    ]
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name='pagamentos')
    forma = models.CharField(max_length=20, choices=FORMA_CHOICES)
    valor = models.DecimalField(max_digits=12, decimal_places=2)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'vendas'

    def __str__(self):
        return f"{self.forma}: R$ {self.valor}"


class OperacaoCaixa(BaseModel):
    TIPO_CHOICES = [('SANGRIA', 'Sangria'), ('SUPRIMENTO', 'Suprimento')]

    sessao = models.ForeignKey(SessaoCaixa, on_delete=models.CASCADE, related_name='operacoes')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    motivo = models.CharField(max_length=255, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'vendas'

    def __str__(self):
        return f"{self.tipo} - R$ {self.valor}"
