import uuid
from datetime import time

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def default_horarios_funcionamento():
    return {
        str(dia): {"aberto": True, "inicio": "06:00", "fim": "20:00"}
        for dia in range(7)
    }


def delivery_esta_aberto(configuracao, agora=None):
    """Verifica o horário semanal, inclusive turnos que cruzam a meia-noite."""
    if not configuracao.aceita_pedidos:
        return False

    local = timezone.localtime(agora) if agora else timezone.localtime()
    horarios = configuracao.horarios_funcionamento or {}
    atual = local.time().replace(second=0, microsecond=0)

    def intervalo(dia):
        faixa = horarios.get(str(dia), {})
        if not faixa.get("aberto"):
            return None
        try:
            return (
                time.fromisoformat(str(faixa.get("inicio", ""))),
                time.fromisoformat(str(faixa.get("fim", ""))),
            )
        except (TypeError, ValueError):
            return None

    hoje = intervalo(local.weekday())
    if hoje:
        inicio, fim = hoje
        if inicio == fim:
            return True
        if inicio < fim and inicio <= atual < fim:
            return True
        if inicio > fim and atual >= inicio:
            return True

    anterior = intervalo((local.weekday() - 1) % 7)
    if not anterior:
        return False
    inicio, fim = anterior
    return inicio > fim and atual < fim


class ConfiguracaoDelivery(models.Model):
    nome_loja = models.CharField(max_length=120, default="Bella Fornada")
    slug = models.SlugField(max_length=120, unique=True, default="bella-fornada")
    whatsapp = models.CharField(
        max_length=20,
        blank=True,
        help_text="Número com DDI e DDD, somente dígitos.",
    )
    pix_chave = models.CharField(max_length=160, blank=True)
    pix_beneficiario = models.CharField(max_length=160, blank=True)
    aceita_pedidos = models.BooleanField(default=True)
    horarios_funcionamento = models.JSONField(default=default_horarios_funcionamento)
    tempo_retirada_minutos = models.PositiveSmallIntegerField(default=30)
    tempo_entrega_minutos = models.PositiveSmallIntegerField(default=50)
    loja_estoque = models.CharField(max_length=100, default="Loja Principal")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuração do delivery"
        verbose_name_plural = "Configurações do delivery"
        ordering = ("id",)

    @classmethod
    def atual(cls):
        configuracao = cls.objects.order_by("id").first()
        if configuracao:
            return configuracao
        return cls.objects.create()

    def __str__(self):
        return self.nome_loja


class BairroEntrega(models.Model):
    nome = models.CharField(max_length=100)
    taxa_entrega = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("ordem", "nome")
        verbose_name = "Bairro de entrega"
        verbose_name_plural = "Bairros de entrega"

    def __str__(self):
        return self.nome


class GrupoComplemento(models.Model):
    nome = models.CharField(max_length=100)
    descricao = models.CharField(max_length=240, blank=True)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("ordem", "nome")
        verbose_name = "Grupo de complementos"
        verbose_name_plural = "Grupos de complementos"

    def __str__(self):
        return self.nome


class Complemento(models.Model):
    grupo = models.ForeignKey(
        GrupoComplemento,
        related_name="complementos",
        on_delete=models.PROTECT,
    )
    nome = models.CharField(max_length=100)
    preco_adicional = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("ordem", "nome")
        constraints = [
            models.UniqueConstraint(
                fields=("grupo", "nome"),
                name="delivery_complemento_unico_grupo",
            )
        ]

    def __str__(self):
        return f"{self.grupo.nome} - {self.nome}"


class ProdutoGrupoComplemento(models.Model):
    produto = models.ForeignKey(
        "produtos.Produto",
        related_name="grupos_complementos_delivery",
        on_delete=models.CASCADE,
    )
    grupo = models.ForeignKey(
        GrupoComplemento,
        related_name="produtos_vinculados",
        on_delete=models.PROTECT,
    )
    minimo_escolhas = models.PositiveSmallIntegerField(default=0)
    maximo_escolhas = models.PositiveSmallIntegerField(default=1)
    ordem = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("ordem", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("produto", "grupo"),
                name="delivery_grupo_unico_produto",
            ),
            models.CheckConstraint(
                condition=models.Q(maximo_escolhas__gte=models.F("minimo_escolhas")),
                name="delivery_limites_escolhas_validos",
            ),
            models.CheckConstraint(
                condition=models.Q(maximo_escolhas__gte=1),
                name="delivery_maximo_escolhas_positivo",
            ),
        ]

    def __str__(self):
        return f"{self.produto} - {self.grupo}"


class Entregador(models.Model):
    nome = models.CharField(max_length=120)
    telefone = models.CharField(max_length=20, blank=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="perfil_entregador",
        on_delete=models.SET_NULL,
    )
    ativo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("nome",)
        verbose_name_plural = "Entregadores"

    def __str__(self):
        return self.nome


class PedidoDelivery(models.Model):
    class TipoAtendimento(models.TextChoices):
        ENTREGA = "ENTREGA", "Entrega"
        RETIRADA = "RETIRADA", "Retirada"

    class FormaPagamento(models.TextChoices):
        PIX = "PIX", "Pix"
        DINHEIRO = "DINHEIRO", "Dinheiro"
        CARTAO = "CARTAO", "Cartão na entrega"

    class Status(models.TextChoices):
        RECEBIDO = "RECEBIDO", "Recebido"
        AGUARDANDO_PAGAMENTO = "AGUARDANDO_PAGAMENTO", "Aguardando pagamento Pix"
        CONFIRMADO = "CONFIRMADO", "Confirmado"
        EM_PREPARO = "EM_PREPARO", "Em preparo"
        PRONTO = "PRONTO", "Pronto"
        SAIU_ENTREGA = "SAIU_ENTREGA", "Saiu para entrega"
        CONCLUIDO = "CONCLUIDO", "Concluído"
        CANCELADO = "CANCELADO", "Cancelado"

    rastreamento_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    idempotency_key = models.CharField(max_length=120, unique=True, editable=False)
    request_fingerprint = models.CharField(max_length=64, editable=False)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.RECEBIDO)
    fulfillment = models.CharField(max_length=10, choices=TipoAtendimento.choices)
    payment_method = models.CharField(max_length=10, choices=FormaPagamento.choices)
    pagamento_confirmado = models.BooleanField(default=False)
    pagamento_confirmado_em = models.DateTimeField(null=True, blank=True)

    nome_cliente = models.CharField(max_length=120)
    telefone_cliente = models.CharField(max_length=20)
    bairro = models.ForeignKey(
        BairroEntrega,
        null=True,
        blank=True,
        related_name="pedidos",
        on_delete=models.PROTECT,
    )
    bairro_nome = models.CharField(max_length=100, blank=True)
    bairro_outro = models.CharField(max_length=100, blank=True)
    cep = models.CharField(max_length=9, blank=True)
    endereco = models.CharField(max_length=200, blank=True)
    numero = models.CharField(max_length=20, blank=True)
    complemento = models.CharField(max_length=120, blank=True)
    referencia = models.CharField(max_length=180, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    troco_para = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    observacoes = models.CharField(max_length=500, blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taxa_entrega = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tempo_estimado_minutos = models.PositiveSmallIntegerField(default=0)

    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="pedidos_delivery_confirmados",
        on_delete=models.PROTECT,
    )
    entregador = models.ForeignKey(
        Entregador,
        null=True,
        blank=True,
        related_name="pedidos",
        on_delete=models.PROTECT,
    )
    venda = models.OneToOneField(
        "vendas.Venda",
        null=True,
        blank=True,
        related_name="pedido_delivery",
        on_delete=models.PROTECT,
    )
    motivo_cancelamento = models.TextField(blank=True)
    concluido_em = models.DateTimeField(null=True, blank=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "created_at"), name="delivery_pedido_status_idx"),
            models.Index(fields=("telefone_cliente",), name="delivery_pedido_fone_idx"),
        ]

    @property
    def bairro_exibicao(self):
        return self.bairro_nome or self.bairro_outro

    def __str__(self):
        return f"Pedido #{self.pk} - {self.nome_cliente}"


class PedidoItem(models.Model):
    pedido = models.ForeignKey(PedidoDelivery, related_name="itens", on_delete=models.PROTECT)
    produto = models.ForeignKey(
        "produtos.Produto",
        related_name="itens_delivery",
        on_delete=models.PROTECT,
    )
    produto_nome = models.CharField(max_length=255)
    unidade_medida = models.CharField(max_length=10, default="UN")
    preco_base_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    preco_complementos_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    quantidade = models.DecimalField(max_digits=10, decimal_places=3)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    observacoes = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.quantidade} x {self.produto_nome}"


class PedidoItemComplemento(models.Model):
    item = models.ForeignKey(PedidoItem, related_name="complementos", on_delete=models.PROTECT)
    complemento = models.ForeignKey(
        Complemento,
        related_name="itens_pedido",
        on_delete=models.PROTECT,
    )
    grupo_nome = models.CharField(max_length=100)
    complemento_nome = models.CharField(max_length=100)
    preco_adicional = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("item", "complemento"),
                name="delivery_complemento_unico_item",
            )
        ]

    def __str__(self):
        return self.complemento_nome


class HistoricoPedido(models.Model):
    class Tipo(models.TextChoices):
        CRIACAO = "CRIACAO", "Criação"
        STATUS = "STATUS", "Mudança de status"
        PAGAMENTO = "PAGAMENTO", "Pagamento"
        ATRIBUICAO = "ATRIBUICAO", "Atribuição de entregador"

    pedido = models.ForeignKey(PedidoDelivery, related_name="historico", on_delete=models.CASCADE)
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.STATUS)
    status_anterior = models.CharField(max_length=32, blank=True)
    status_novo = models.CharField(max_length=32, blank=True)
    observacao = models.CharField(max_length=500, blank=True)
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="historico_pedidos_delivery",
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self):
        return f"Pedido #{self.pedido_id}: {self.status_anterior} → {self.status_novo}"
