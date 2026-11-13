import binascii
import logging
import re

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.fiscal.models import (
    ConfiguracaoFiscal,
    DocumentoFiscal,
    EventoFiscal,
    InutilizacaoNumeracao,
    TentativaFiscal,
)

from .client import FiscalBinaryResponse, GeranetClient
from .errors import FiscalConflictError, FiscalValidationError, GeranetAPIError
from .payloads import InutilizacaoFiscalPayloadBuilder, VendaFiscalPayloadBuilder
from .security import extract_safe_error, sanitize_text

logger = logging.getLogger(__name__)
REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


class FiscalService:
    def __init__(self, *, client=None):
        self._client = client

    @staticmethod
    def default_reference(venda, tipo):
        return f"venda:{venda.id_externo}:{tipo.lower()}"

    @staticmethod
    def normalize_reference(reference):
        reference = str(reference or "").strip()
        if not REFERENCE_RE.fullmatch(reference):
            raise FiscalValidationError("A referência fiscal informada é inválida.")
        return reference

    def _client_for(self, config):
        return self._client or GeranetClient(config)

    def emitir(self, *, venda, tipo, usuario=None, canal=DocumentoFiscal.Canal.PDV,
               pedido_delivery_id=None, referencia=None):
        tipo = str(tipo).upper()
        if tipo not in DocumentoFiscal.Tipo.values:
            raise FiscalValidationError("Tipo de documento fiscal inválido.")
        reference = self.normalize_reference(referencia or self.default_reference(venda, tipo))
        existing = DocumentoFiscal.all_objects.filter(referencia=reference).first()
        if existing:
            if existing.venda_id != venda.pk or existing.tipo != tipo:
                raise FiscalConflictError("A referência fiscal já está em uso.")
            if existing.status == DocumentoFiscal.Status.REJEITADA:
                return self._retry_rejected(existing, venda=venda, usuario=usuario)
            return existing, False

        try:
            with transaction.atomic():
                config = ConfiguracaoFiscal.objects.select_for_update().get(pk=ConfiguracaoFiscal.atual().pk)
                number_field = "proximo_numero_nfce" if tipo == "NFCE" else "proximo_numero_nfe"
                series_field = "serie_nfce" if tipo == "NFCE" else "serie_nfe"
                number, series = getattr(config, number_field), getattr(config, series_field)
                builder = VendaFiscalPayloadBuilder(
                    venda, tipo=tipo, canal=canal, configuracao=config,
                    numero=number, serie=series, referencia=reference,
                )
                payload = builder.build()
                document = DocumentoFiscal.objects.create(
                    venda=venda, pedido_delivery_id=pedido_delivery_id, canal=canal,
                    tipo=tipo, status=DocumentoFiscal.Status.PROCESSANDO,
                    ambiente=config.ambiente, referencia=reference,
                    valor_total=venda.total_liquido, numero=str(number), serie=series,
                    solicitada_por=usuario if getattr(usuario, "is_authenticated", False) else None,
                )
                setattr(config, number_field, number + 1)
                config.save(update_fields=[number_field, "updated_at"])
                EventoFiscal.objects.create(
                    documento=document, tipo=EventoFiscal.Tipo.EMISSAO_SOLICITADA,
                    status_anterior=DocumentoFiscal.Status.PENDENTE,
                    status_novo=DocumentoFiscal.Status.PROCESSANDO,
                    descricao="Emissão fiscal solicitada à Geranet.",
                )
                attempt = TentativaFiscal.objects.create(documento=document, operacao=TentativaFiscal.Operacao.EMISSAO)
        except IntegrityError:
            existing = DocumentoFiscal.all_objects.filter(referencia=reference).first()
            if existing:
                return existing, False
            raise

        try:
            response = self._client_for(config).emitir(payload)
        except GeranetAPIError as exc:
            self._finish_error(document, attempt, exc, mark_document_error=True)
            raise
        document = self._apply_response(document, response.data, response.status_code, cancellation=False)
        self._finish_success(attempt, response)
        return document, True

    def _retry_rejected(self, document, *, venda, usuario=None):
        with transaction.atomic():
            document = DocumentoFiscal.all_objects.select_for_update().get(pk=document.pk)
            if document.status != DocumentoFiscal.Status.REJEITADA:
                return document, False

            config = ConfiguracaoFiscal.objects.select_for_update().get(
                pk=ConfiguracaoFiscal.atual().pk
            )
            if document.ambiente != config.ambiente:
                raise FiscalConflictError(
                    "O documento foi emitido em outro ambiente fiscal. "
                    "Altere a configuração para o ambiente original antes de reenviar."
                )
            builder = VendaFiscalPayloadBuilder(
                venda,
                tipo=document.tipo,
                canal=document.canal,
                configuracao=config,
                numero=document.numero,
                serie=document.serie,
                referencia=document.referencia,
            )
            payload = builder.build()
            old_status = document.status
            document.status = DocumentoFiscal.Status.PROCESSANDO
            document.codigo_status = ""
            document.mensagem_sefaz = ""
            if getattr(usuario, "is_authenticated", False):
                document.solicitada_por = usuario
            document.save(
                update_fields=[
                    "status",
                    "codigo_status",
                    "mensagem_sefaz",
                    "solicitada_por",
                    "updated_at",
                ]
            )
            EventoFiscal.objects.create(
                documento=document,
                tipo=EventoFiscal.Tipo.EMISSAO_SOLICITADA,
                status_anterior=old_status,
                status_novo=DocumentoFiscal.Status.PROCESSANDO,
                descricao="Reenvio de documento rejeitado solicitado à Geranet.",
            )
            attempt = TentativaFiscal.objects.create(
                documento=document,
                operacao=TentativaFiscal.Operacao.EMISSAO,
            )

        try:
            response = self._client_for(config).emitir(payload)
        except GeranetAPIError as exc:
            self._finish_error(document, attempt, exc, mark_document_error=True)
            raise
        document = self._apply_response(
            document,
            response.data,
            response.status_code,
            cancellation=False,
        )
        self._finish_success(attempt, response)
        return document, False

    def sincronizar(self, document):
        raise FiscalConflictError("A Geranet responde de forma síncrona; o documento já está atualizado.")

    def cancelar(self, document, justificativa):
        justificativa = sanitize_text(justificativa, max_length=255)
        if len(justificativa) < 15:
            raise FiscalValidationError("A justificativa deve ter no mínimo 15 caracteres.")
        if document.status != DocumentoFiscal.Status.AUTORIZADA:
            raise FiscalConflictError("Somente documentos autorizados podem ser cancelados.")
        if not document.chave_acesso or not document.protocolo:
            raise FiscalConflictError("O documento não possui chave e protocolo para cancelamento.")
        config = ConfiguracaoFiscal.atual()
        builder = VendaFiscalPayloadBuilder(
            document.venda, tipo=document.tipo, canal=document.canal, configuracao=config,
            numero=document.numero, serie=document.serie, referencia=document.referencia,
        )
        payload = builder.build_cancellation(document, justificativa)
        EventoFiscal.objects.create(
            documento=document, tipo=EventoFiscal.Tipo.CANCELAMENTO_SOLICITADO,
            status_anterior=document.status, status_novo=document.status,
            descricao="Cancelamento fiscal solicitado à Geranet.",
        )
        attempt = TentativaFiscal.objects.create(documento=document, operacao=TentativaFiscal.Operacao.CANCELAMENTO)
        try:
            response = self._client_for(config).cancelar(payload)
        except GeranetAPIError as exc:
            self._finish_error(document, attempt, exc, mark_document_error=False)
            raise
        if str(response.data.get("situacao", "")).lower() != "sucesso" or str(response.data.get("cstat", "")) != "135":
            error = GeranetAPIError(extract_safe_error(response.data, fallback="A Geranet não confirmou o cancelamento."))
            self._finish_error(document, attempt, error, mark_document_error=False)
            raise error
        document = self._apply_response(document, response.data, response.status_code, cancellation=True)
        self._finish_success(attempt, response)
        return document

    def inutilizar_numeracao(
        self,
        *,
        tipo,
        serie,
        ano,
        numero_inicial,
        numero_final,
        justificativa,
        usuario=None,
    ):
        tipo = str(tipo).upper()
        serie = str(serie).strip()
        justificativa = sanitize_text(justificativa, max_length=255)
        if tipo not in DocumentoFiscal.Tipo.values:
            raise FiscalValidationError("Tipo de documento fiscal inválido.")
        if not serie.isdigit() or not 1 <= int(serie) <= 999:
            raise FiscalValidationError("A série deve ser um número entre 1 e 999.")
        serie = str(int(serie))
        if not 2000 <= int(ano) <= 2099:
            raise FiscalValidationError("Informe o ano completo entre 2000 e 2099.")
        if numero_inicial < 1 or numero_final < numero_inicial:
            raise FiscalValidationError("A faixa de numeração é inválida.")
        if len(justificativa) < 15:
            raise FiscalValidationError("A justificativa deve ter no mínimo 15 caracteres.")

        config = ConfiguracaoFiscal.atual()
        documents = DocumentoFiscal.all_objects.filter(
            tipo=tipo,
            ambiente=config.ambiente,
            serie=serie,
            status__in=[
                DocumentoFiscal.Status.AUTORIZADA,
                DocumentoFiscal.Status.CANCELADA,
            ],
        ).values_list("numero", flat=True)
        conflicts = sorted(
            int(number)
            for number in documents
            if str(number).isdigit() and numero_inicial <= int(number) <= numero_final
        )
        if conflicts:
            raise FiscalConflictError(
                "A faixa contém número autorizado ou cancelado no sistema: "
                + ", ".join(str(number) for number in conflicts[:10])
                + "."
            )

        overlapping = InutilizacaoNumeracao.objects.filter(
            tipo=tipo,
            ambiente=config.ambiente,
            serie=serie,
            ano=ano,
            status__in=[
                InutilizacaoNumeracao.Status.PROCESSANDO,
                InutilizacaoNumeracao.Status.INUTILIZADA,
            ],
            numero_inicial__lte=numero_final,
            numero_final__gte=numero_inicial,
        ).exists()
        if overlapping:
            raise FiscalConflictError("A faixa informada já foi inutilizada ou está em processamento.")

        payload = InutilizacaoFiscalPayloadBuilder(config).build(
            tipo=tipo,
            serie=serie,
            ano=ano,
            numero_inicial=numero_inicial,
            numero_final=numero_final,
            justificativa=justificativa,
        )
        record = InutilizacaoNumeracao.objects.create(
            tipo=tipo,
            ambiente=config.ambiente,
            serie=serie,
            ano=ano,
            numero_inicial=numero_inicial,
            numero_final=numero_final,
            justificativa=justificativa,
            solicitada_por=usuario if getattr(usuario, "is_authenticated", False) else None,
        )
        try:
            response = self._client_for(config).inutilizar_numeracao(payload)
        except GeranetAPIError as exc:
            record.status = InutilizacaoNumeracao.Status.ERRO
            record.mensagem_sefaz = sanitize_text(exc.message, max_length=500)
            record.save(update_fields=["status", "mensagem_sefaz", "updated_at"])
            raise

        data = response.data
        successful = (
            str(data.get("situacao", "")).lower() == "sucesso"
            and str(data.get("cstat", "")) == "102"
        )
        record.status = (
            InutilizacaoNumeracao.Status.INUTILIZADA
            if successful
            else InutilizacaoNumeracao.Status.REJEITADA
        )
        record.codigo_status = self._safe(data.get("cstat"), 20)
        record.mensagem_sefaz = sanitize_text(data.get("mensagem", ""), max_length=500)
        record.protocolo = self._safe(data.get("protocolo"), 50)
        try:
            record.xml_conteudo = self._decode_hex(data.get("xml"), "XML")
        except GeranetAPIError as exc:
            record.status = InutilizacaoNumeracao.Status.ERRO
            record.mensagem_sefaz = sanitize_text(exc.message, max_length=500)
            record.save(update_fields=["status", "mensagem_sefaz", "updated_at"])
            raise
        record.save()
        return record

    def baixar_xml(self, document):
        if not document.xml_conteudo:
            raise FiscalConflictError("O XML ainda não está disponível.")
        return FiscalBinaryResponse(bytes(document.xml_conteudo), "application/xml")

    def baixar_pdf(self, document):
        if not document.pdf_conteudo:
            raise FiscalConflictError("O PDF ainda não está disponível.")
        return FiscalBinaryResponse(bytes(document.pdf_conteudo), "application/pdf")

    @staticmethod
    def _decode_hex(value, label):
        value = str(value or "").strip()
        if not value:
            return None
        if len(value) > MAX_DOCUMENT_BYTES * 2:
            raise GeranetAPIError(f"O {label} retornado excede o limite permitido.")
        try:
            return binascii.unhexlify(value)
        except (binascii.Error, ValueError) as exc:
            raise GeranetAPIError(f"A Geranet retornou {label} inválido.") from exc

    def _apply_response(self, document, data, http_status, *, cancellation):
        success_code = "135" if cancellation else "100"
        successful = str(data.get("situacao", "")).lower() == "sucesso" and str(data.get("cstat", "")) == success_code
        new_status = (DocumentoFiscal.Status.CANCELADA if cancellation else DocumentoFiscal.Status.AUTORIZADA) if successful else DocumentoFiscal.Status.REJEITADA
        xml, pdf = self._decode_hex(data.get("xml"), "XML"), self._decode_hex(data.get("pdf"), "PDF")
        now = timezone.now()
        with transaction.atomic():
            locked = DocumentoFiscal.all_objects.select_for_update().get(pk=document.pk)
            old_status = locked.status
            locked.status = new_status
            locked.chave_acesso = self._safe(data.get("chave"), 44) or locked.chave_acesso
            locked.protocolo = self._safe(data.get("protocolo"), 50) or locked.protocolo
            locked.numero = self._safe(data.get("numero"), 20) or locked.numero
            locked.codigo_status = self._safe(data.get("cstat"), 20)
            locked.mensagem_sefaz = sanitize_text(data.get("mensagem", ""), max_length=500)
            if xml is not None:
                locked.xml_conteudo = xml
            if pdf is not None:
                locked.pdf_conteudo = pdf
            if new_status == DocumentoFiscal.Status.AUTORIZADA:
                locked.autorizada_em = locked.autorizada_em or now
            if new_status == DocumentoFiscal.Status.CANCELADA:
                locked.cancelada_em = locked.cancelada_em or now
            locked.save()
            if old_status != new_status:
                EventoFiscal.objects.create(
                    documento=locked, tipo=EventoFiscal.Tipo.STATUS_ALTERADO,
                    status_anterior=old_status, status_novo=new_status,
                    descricao="Status atualizado pela resposta da Geranet.",
                )
        return locked

    @staticmethod
    def _safe(value, length):
        return sanitize_text(value or "", max_length=length)

    @staticmethod
    def _finish_success(attempt, response):
        TentativaFiscal.objects.filter(pk=attempt.pk).update(
            resultado=TentativaFiscal.Resultado.SUCESSO, http_status=response.status_code,
            status_remoto=sanitize_text(response.data.get("situacao", ""), max_length=30),
            finalizada_em=timezone.now(),
        )

    @staticmethod
    def _finish_error(document, attempt, error, *, mark_document_error):
        message = sanitize_text(getattr(error, "message", str(error)), max_length=500)
        TentativaFiscal.objects.filter(pk=attempt.pk).update(
            resultado=TentativaFiscal.Resultado.ERRO,
            http_status=getattr(error, "upstream_status", None),
            codigo_erro=sanitize_text(getattr(error, "code", "fiscal_error"), max_length=50),
            mensagem=message, finalizada_em=timezone.now(),
        )
        if mark_document_error:
            DocumentoFiscal.all_objects.filter(pk=document.pk).update(
                status=DocumentoFiscal.Status.ERRO, mensagem_sefaz=message
            )
