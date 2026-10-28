from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import ActiveManager, BaseModel
from apps.produtos.models import Produto


class Receita(BaseModel):
    produto = models.OneToOneField(
        Produto,
        on_delete=models.PROTECT,
        related_name='receita_producao',
    )
    nome = models.CharField(max_length=160)
    rendimento = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Quantidade produzida por fornada/lote.',
    )
    unidade_rendimento = models.CharField(max_length=10, default='UN')
    tempo_preparo_minutos = models.PositiveIntegerField(default=60)
    instrucoes = models.TextField(blank=True)
    ativa = models.BooleanField(default=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ('nome',)

    def __str__(self):
        return self.nome


class ReceitaIngrediente(BaseModel):
    receita = models.ForeignKey(
        Receita,
        on_delete=models.CASCADE,
        related_name='ingredientes',
    )
    ingrediente = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        related_name='uso_em_receitas',
    )
    quantidade = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
    )
    percentual_perda = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
    )

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ('ingrediente__nome',)
        constraints = [
            models.UniqueConstraint(
                fields=('receita', 'ingrediente'),
                condition=models.Q(is_deleted=False),
                name='uniq_ingrediente_ativo_por_receita',
            )
        ]

    @property
    def quantidade_com_perda(self):
        return self.quantidade * (
            Decimal('1') + (self.percentual_perda / Decimal('100'))
        )


class OrdemProducao(BaseModel):
    class Status(models.TextChoices):
        PLANEJADA = 'PLANEJADA', 'Planejada'
        EM_PRODUCAO = 'EM_PRODUCAO', 'Em produção'
        CONCLUIDA = 'CONCLUIDA', 'Concluída'
        CANCELADA = 'CANCELADA', 'Cancelada'

    receita = models.ForeignKey(
        Receita,
        on_delete=models.PROTECT,
        related_name='ordens',
    )
    quantidade_lotes = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=1,
        validators=[MinValueValidator(Decimal('0.001'))],
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PLANEJADA,
    )
    data_planejada = models.DateTimeField()
    iniciada_em = models.DateTimeField(null=True, blank=True)
    concluida_em = models.DateTimeField(null=True, blank=True)
    criada_por = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='ordens_producao_criadas',
    )
    concluida_por = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='ordens_producao_concluidas',
    )
    codigo_lote = models.CharField(max_length=40, blank=True)
    data_validade = models.DateField(null=True, blank=True)
    quantidade_produzida = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
    )
    observacoes = models.TextField(blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ('-data_planejada', '-created_at')

    @property
    def quantidade_prevista(self):
        return self.receita.rendimento * self.quantidade_lotes

    def __str__(self):
        return f'{self.receita.nome} — {self.get_status_display()}'


class PerdaProducao(BaseModel):
    class Motivo(models.TextChoices):
        VENCIMENTO = 'VENCIMENTO', 'Vencimento'
        AVARIA = 'AVARIA', 'Avaria'
        ERRO_PRODUCAO = 'ERRO_PRODUCAO', 'Erro de produção'
        SOBRA = 'SOBRA', 'Sobra não aproveitada'
        OUTRO = 'OUTRO', 'Outro'

    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        related_name='perdas_producao',
    )
    quantidade = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
    )
    motivo = models.CharField(max_length=20, choices=Motivo.choices)
    observacoes = models.TextField(blank=True)
    registrada_por = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='perdas_producao_registradas',
    )

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ('-created_at',)

