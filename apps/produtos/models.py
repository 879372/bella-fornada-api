from django.db import models
from apps.core.models import BaseModel, ActiveManager

class Grupo(BaseModel):
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True, null=True)
    ativo = models.BooleanField(default=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'produtos'
        verbose_name = 'Grupo'
        verbose_name_plural = 'Grupos'
        ordering = ['nome']

    def __str__(self):
        return self.nome

class Produto(BaseModel):
    codigo_legado = models.IntegerField(unique=True, null=True, blank=True, help_text="Código da Mercadoria no sistema legado")
    nome = models.CharField(max_length=255)
    codigo_barras = models.CharField(max_length=100, blank=True, null=True)

    # Preços
    preco_compra = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    preco_venda = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Detalhes
    unidade_medida = models.CharField(max_length=10, default='UN')
    grupo = models.CharField(max_length=100, blank=True, null=True)
    subgrupo = models.CharField(max_length=100, blank=True, null=True)
    ativo = models.BooleanField(default=True)

    # Cardápio online / delivery
    descricao_delivery = models.TextField(blank=True)
    disponivel_delivery = models.BooleanField(default=False)
    imagem_url = models.URLField(blank=True)
    tempo_preparo_minutos = models.PositiveSmallIntegerField(default=15)

    # Classificação fiscal. As alíquotas e códigos devem ser homologados pelo
    # contador da empresa antes de ativar emissão em produção.
    ncm = models.CharField(max_length=8, blank=True)
    cest = models.CharField(max_length=7, blank=True)
    cfop = models.CharField(max_length=4, default='5102')
    cst_icms = models.CharField(max_length=3, default='102')
    origem_mercadoria = models.CharField(max_length=1, default='0')
    aliquota_icms = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    aliquota_pis = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    aliquota_cofins = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'produtos'

    def save(self, *args, **kwargs):
        if not self.codigo_legado:
            # Pegar o maior código legado e somar 1
            last_product = Produto.all_objects.order_by('-codigo_legado').first()
            if last_product and last_product.codigo_legado:
                self.codigo_legado = last_product.codigo_legado + 1
            else:
                self.codigo_legado = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo_legado} - {self.nome}"

class EstoqueLoja(BaseModel):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='estoques')
    loja = models.CharField(max_length=100)
    quantidade = models.DecimalField(max_digits=15, decimal_places=3, default=0)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        unique_together = ('produto', 'loja')
        app_label = 'produtos'

    def __str__(self):
        return f"{self.produto.nome} - {self.loja}: {self.quantidade}"

class MovimentacaoEstoque(BaseModel):
    TIPO_CHOICES = [('ENTRADA', 'Entrada'), ('SAIDA', 'Saída')]
    MOTIVO_CHOICES = [
        ('VENDA', 'Venda'),
        ('COMPRA', 'Compra'),
        ('AJUSTE', 'Ajuste Manual'),
        ('DEVOLUCAO', 'Devolução'),
        ('PRODUCAO', 'Produção'),
        ('QUEBRA', 'Quebra / perda'),
        ('OUTRO', 'Outro'),
    ]

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='movimentacoes')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    motivo = models.CharField(max_length=20, choices=MOTIVO_CHOICES)
    quantidade = models.DecimalField(max_digits=15, decimal_places=3)
    saldo_anterior = models.DecimalField(max_digits=15, decimal_places=3)
    saldo_atual = models.DecimalField(max_digits=15, decimal_places=3, default=0)
    observacoes = models.TextField(blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = 'produtos'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.produto.nome} ({self.tipo}): {self.quantidade}"
