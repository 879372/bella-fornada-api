from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
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


class ConfiguracaoBalanca(models.Model):
    nome = models.CharField(max_length=100, default='Balança principal')
    fabricante = models.CharField(max_length=50, default='Toledo')
    modelo = models.CharField(max_length=100, blank=True)
    versao_mgv = models.CharField(max_length=50, blank=True)
    ip = models.GenericIPAddressField(protocol='IPv4', blank=True, null=True)
    porta = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(65535)],
        help_text='Use zero quando a comunicação for gerenciada pelo MGV.',
    )
    departamento = models.PositiveSmallIntegerField(default=1)
    validade_padrao_dias = models.PositiveSmallIntegerField(default=1)
    prefixo_ean = models.CharField(max_length=1, default='2')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração da balança'
        verbose_name_plural = 'Configurações da balança'

    @classmethod
    def atual(cls):
        configuracao = cls.objects.order_by('id').first()
        return configuracao or cls.objects.create()

    def __str__(self):
        return self.nome

class Produto(BaseModel):
    class TipoOrigemComercial(models.TextChoices):
        FABRICACAO_PROPRIA = 'FABRICACAO_PROPRIA', 'Fabricação própria'
        REVENDA = 'REVENDA', 'Revenda'
        INSUMO = 'INSUMO', 'Insumo'
        MISTO = 'MISTO', 'Uso misto'
        NAO_CLASSIFICADO = 'NAO_CLASSIFICADO', 'Não classificado'

    class ConfiancaFiscal(models.TextChoices):
        ALTA = 'ALTA', 'Alta'
        MEDIA = 'MEDIA', 'Média'
        BAIXA = 'BAIXA', 'Baixa'
        NAO_REVISADO = 'NAO_REVISADO', 'Não revisado'

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
    marca = models.CharField(max_length=100, blank=True)
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
    cst_pis = models.CharField(max_length=2, blank=True)
    cst_cofins = models.CharField(max_length=2, blank=True)
    origem_mercadoria = models.CharField(max_length=1, default='0')
    codigo_beneficio_fiscal = models.CharField(max_length=10, blank=True)
    unidade_tributavel = models.CharField(max_length=6, blank=True)
    gtin_tributavel = models.CharField(max_length=14, blank=True)
    fator_conversao_tributavel = models.DecimalField(
        max_digits=15, decimal_places=6, default=1
    )
    aliquota_icms = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    aliquota_pis = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    aliquota_cofins = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tipo_origem_comercial = models.CharField(
        max_length=24,
        choices=TipoOrigemComercial.choices,
        default=TipoOrigemComercial.NAO_CLASSIFICADO,
    )
    fiscal_confianca = models.CharField(
        max_length=16,
        choices=ConfiancaFiscal.choices,
        default=ConfiancaFiscal.NAO_REVISADO,
    )
    fiscal_fonte = models.TextField(blank=True)
    fiscal_observacao = models.TextField(blank=True)
    fiscal_revisado_em = models.DateTimeField(null=True, blank=True)

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


class LoteRevisaoFiscal(BaseModel):
    class Status(models.TextChoices):
        APLICADO = 'APLICADO', 'Aplicado'
        REVERTIDO = 'REVERTIDO', 'Revertido'

    status = models.CharField(max_length=12, choices=Status.choices)
    catalogo_checksum = models.CharField(max_length=64)
    mapeamento_checksum = models.CharField(max_length=64)
    fonte = models.TextField(blank=True)
    observacao = models.TextField(blank=True)
    revertido_em = models.DateTimeField(null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ('-created_at',)


class ItemRevisaoFiscal(BaseModel):
    lote = models.ForeignKey(
        LoteRevisaoFiscal,
        on_delete=models.PROTECT,
        related_name='itens',
    )
    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        related_name='revisoes_fiscais',
    )
    codigo_legado = models.IntegerField()
    nome = models.CharField(max_length=255)
    antes = models.JSONField()
    depois = models.JSONField()

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('lote', 'produto'),
                name='uniq_produto_por_lote_revisao_fiscal',
            )
        ]

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
