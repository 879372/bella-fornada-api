import uuid

from django.conf import settings
from django.db import models

from apps.core.models import ActiveManager, BaseModel


class DocumentoFiscal(BaseModel):
    class Tipo(models.TextChoices):
        NFCE = "NFCE", "NFC-e"
        NFE = "NFE", "NF-e"

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        PROCESSANDO = "PROCESSANDO", "Processando"
        AUTORIZADA = "AUTORIZADA", "Autorizada"
        REJEITADA = "REJEITADA", "Rejeitada"
        CANCELADA = "CANCELADA", "Cancelada"
        ERRO = "ERRO", "Erro"

    class Ambiente(models.TextChoices):
        HOMOLOGACAO = "homologacao", "Homologação"
        PRODUCAO = "producao", "Produção"

    class Canal(models.TextChoices):
        PDV = "PDV", "PDV"
        DELIVERY = "DELIVERY", "Delivery"

    venda = models.ForeignKey(
        "vendas.Venda",
        on_delete=models.PROTECT,
        related_name="documentos_fiscais",
        null=True,
        blank=True,
    )
    # O delivery vive em um app separado. O UUID preserva a origem sem criar
    # dependência circular entre os dois domínios.
    pedido_delivery_id = models.UUIDField(null=True, blank=True, db_index=True)
    canal = models.CharField(max_length=10, choices=Canal.choices, default=Canal.PDV)

    tipo = models.CharField(max_length=4, choices=Tipo.choices)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDENTE,
        db_index=True,
    )
    ambiente = models.CharField(
        max_length=12,
        choices=Ambiente.choices,
        default=Ambiente.HOMOLOGACAO,
    )

    # Chave de idempotência do ERP. Nunca é a chave de acesso da SEFAZ.
    referencia = models.CharField(max_length=100, unique=True)
    acbr_id = models.UUIDField(null=True, blank=True, unique=True)
    chave_acesso = models.CharField(max_length=44, blank=True)
    numero = models.CharField(max_length=20, blank=True)
    serie = models.CharField(max_length=5, blank=True)
    protocolo = models.CharField(max_length=50, blank=True)
    codigo_status = models.CharField(max_length=20, blank=True)
    mensagem_sefaz = models.CharField(max_length=500, blank=True)
    valor_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    solicitada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="documentos_fiscais_solicitados",
        null=True,
        blank=True,
    )
    autorizada_em = models.DateTimeField(null=True, blank=True)
    cancelada_em = models.DateTimeField(null=True, blank=True)
    ultima_sincronizacao_em = models.DateTimeField(null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        app_label = "fiscal"
        ordering = ["-created_at"]
        verbose_name = "Documento fiscal"
        verbose_name_plural = "Documentos fiscais"
        indexes = [
            models.Index(fields=["tipo", "status"], name="fiscal_doc_tipo_status_idx"),
            models.Index(fields=["venda", "status"], name="fiscal_doc_venda_status_idx"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.referencia} ({self.get_status_display()})"


class TentativaFiscal(models.Model):
    class Operacao(models.TextChoices):
        EMISSAO = "EMISSAO", "Emissão"
        SINCRONIZACAO = "SINCRONIZACAO", "Sincronização"
        CANCELAMENTO = "CANCELAMENTO", "Cancelamento"
        DOWNLOAD_XML = "DOWNLOAD_XML", "Download de XML"
        DOWNLOAD_PDF = "DOWNLOAD_PDF", "Download de PDF"

    class Resultado(models.TextChoices):
        PROCESSANDO = "PROCESSANDO", "Processando"
        SUCESSO = "SUCESSO", "Sucesso"
        ERRO = "ERRO", "Erro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    documento = models.ForeignKey(
        DocumentoFiscal,
        on_delete=models.CASCADE,
        related_name="tentativas",
    )
    operacao = models.CharField(max_length=20, choices=Operacao.choices)
    resultado = models.CharField(
        max_length=12,
        choices=Resultado.choices,
        default=Resultado.PROCESSANDO,
    )
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    status_remoto = models.CharField(max_length=30, blank=True)
    codigo_erro = models.CharField(max_length=50, blank=True)
    mensagem = models.CharField(max_length=500, blank=True)
    iniciada_em = models.DateTimeField(auto_now_add=True)
    finalizada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "fiscal"
        ordering = ["-iniciada_em"]
        verbose_name = "Tentativa fiscal"
        verbose_name_plural = "Tentativas fiscais"
        indexes = [
            models.Index(
                fields=["documento", "operacao", "-iniciada_em"],
                name="fiscal_tent_doc_op_idx",
            )
        ]

    def __str__(self):
        return f"{self.operacao} - {self.documento.referencia} - {self.resultado}"


class EventoFiscal(models.Model):
    class Tipo(models.TextChoices):
        STATUS_ALTERADO = "STATUS_ALTERADO", "Status alterado"
        EMISSAO_SOLICITADA = "EMISSAO_SOLICITADA", "Emissão solicitada"
        SINCRONIZADO = "SINCRONIZADO", "Sincronizado"
        CANCELAMENTO_SOLICITADO = "CANCELAMENTO_SOLICITADO", "Cancelamento solicitado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    documento = models.ForeignKey(
        DocumentoFiscal,
        on_delete=models.CASCADE,
        related_name="eventos",
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    status_anterior = models.CharField(max_length=12, blank=True)
    status_novo = models.CharField(max_length=12, blank=True)
    descricao = models.CharField(max_length=300, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "fiscal"
        ordering = ["-criado_em"]
        verbose_name = "Evento fiscal"
        verbose_name_plural = "Eventos fiscais"
        indexes = [
            models.Index(fields=["documento", "-criado_em"], name="fiscal_event_doc_idx")
        ]

    def __str__(self):
        return f"{self.tipo} - {self.documento.referencia}"

