import logging
import re
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.fiscal.models import DocumentoFiscal, EventoFiscal, TentativaFiscal

from .client import ACBRAPIClient
from .errors import ACBRAPIError, FiscalConflictError, FiscalValidationError
from .payloads import VendaFiscalPayloadBuilder
from .security import extract_safe_error, sanitize_text


logger = logging.getLogger(__name__)
REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")


REMOTE_STATUS_MAP = {
    "pendente": DocumentoFiscal.Status.PENDENTE,
    "processando": DocumentoFiscal.Status.PROCESSANDO,
    "autorizada": DocumentoFiscal.Status.AUTORIZADA,
    "autorizado": DocumentoFiscal.Status.AUTORIZADA,
    "rejeitada": DocumentoFiscal.Status.REJEITADA,
    "rejeitado": DocumentoFiscal.Status.REJEITADA,
    "cancelada": DocumentoFiscal.Status.CANCELADA,
    "cancelado": DocumentoFiscal.Status.CANCELADA,
    "erro": DocumentoFiscal.Status.ERRO,
}


class FiscalService:
    def __init__(self, *, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = ACBRAPIClient()
        return self._client

    @staticmethod
    def default_reference(venda, tipo):
        return f"venda:{venda.id_externo}:{tipo.lower()}"

    @staticmethod
    def normalize_reference(reference):
        reference = str(reference or "").strip()
        if not REFERENCE_RE.fullmatch(reference):
            raise FiscalValidationError(
                "A referência deve ter até 100 caracteres e usar apenas letras, "
                "números, ponto, sublinhado, dois-pontos ou hífen."
            )
        return reference

    def emitir(
        self,
        *,
        venda,
        tipo,
        usuario=None,
        canal=DocumentoFiscal.Canal.PDV,
        pedido_delivery_id=None,
        referencia=None,
    ):
        tipo = str(tipo).upper()
        if tipo not in DocumentoFiscal.Tipo.values:
            raise FiscalValidationError("Tipo de documento fiscal inválido.")
        if canal not in DocumentoFiscal.Canal.values:
            raise FiscalValidationError("Canal fiscal inválido.")

        reference = self.normalize_reference(
            referencia or self.default_reference(venda, tipo)
        )
        existing = DocumentoFiscal.all_objects.filter(referencia=reference).first()
        if existing:
            if existing.venda_id != venda.pk or existing.tipo != tipo:
                raise FiscalConflictError("A referência fiscal já está em uso.")
            return existing, False

        ambiente = getattr(settings, "FISCAL_AMBIENTE", "homologacao")
        builder = VendaFiscalPayloadBuilder(
            venda,
            tipo=tipo,
            canal=canal,
            ambiente=ambiente,
            referencia=reference,
        )
        payload = builder.build()

        try:
            with transaction.atomic():
                document = DocumentoFiscal.objects.create(
                    venda=venda,
                    pedido_delivery_id=pedido_delivery_id,
                    canal=canal,
                    tipo=tipo,
                    status=DocumentoFiscal.Status.PROCESSANDO,
                    ambiente=ambiente,
                    referencia=reference,
                    valor_total=venda.total_liquido,
                    solicitada_por=usuario if getattr(usuario, "is_authenticated", False) else None,
                )
                EventoFiscal.objects.create(
                    documento=document,
                    tipo=EventoFiscal.Tipo.EMISSAO_SOLICITADA,
                    status_anterior=DocumentoFiscal.Status.PENDENTE,
                    status_novo=DocumentoFiscal.Status.PROCESSANDO,
                    descricao="Emissão fiscal solicitada.",
                )
                attempt = TentativaFiscal.objects.create(
                    documento=document,
                    operacao=TentativaFiscal.Operacao.EMISSAO,
                )
        except IntegrityError:
            existing = DocumentoFiscal.all_objects.filter(referencia=reference).first()
            if existing:
                return existing, False
            raise

        try:
            response = self.client.emitir(tipo, payload)
        except ACBRAPIError as exc:
            self._finish_error(document, attempt, exc, mark_document_error=True)
            raise

        document = self._apply_remote_response(
            document,
            response.data,
            http_status=response.status_code,
            operation=TentativaFiscal.Operacao.EMISSAO,
        )
        self._finish_success(attempt, response)
        return document, True

    def sincronizar(self, document):
        if not document.acbr_id:
            raise FiscalConflictError(
                "O documento ainda não possui identificador da ACBRAPI para sincronização."
            )
        attempt = TentativaFiscal.objects.create(
            documento=document,
            operacao=TentativaFiscal.Operacao.SINCRONIZACAO,
        )
        try:
            response = self.client.consultar_nota(document.acbr_id)
        except ACBRAPIError as exc:
            self._finish_error(document, attempt, exc, mark_document_error=False)
            raise

        document = self._apply_remote_response(
            document,
            response.data,
            http_status=response.status_code,
            operation=TentativaFiscal.Operacao.SINCRONIZACAO,
        )
        DocumentoFiscal.all_objects.filter(pk=document.pk).update(
            ultima_sincronizacao_em=timezone.now()
        )
        document.refresh_from_db()
        self._finish_success(attempt, response)
        EventoFiscal.objects.create(
            documento=document,
            tipo=EventoFiscal.Tipo.SINCRONIZADO,
            status_novo=document.status,
            descricao="Metadados sincronizados com a ACBRAPI.",
        )
        return document

    def cancelar(self, document, justificativa):
        justificativa = sanitize_text(justificativa, max_length=255)
        if len(justificativa) < 15:
            raise FiscalValidationError(
                "A justificativa de cancelamento deve ter no mínimo 15 caracteres."
            )
        if document.status != DocumentoFiscal.Status.AUTORIZADA:
            raise FiscalConflictError("Somente documentos autorizados podem ser cancelados.")
        if not document.acbr_id:
            raise FiscalConflictError("O documento não possui identificador da ACBRAPI.")

        EventoFiscal.objects.create(
            documento=document,
            tipo=EventoFiscal.Tipo.CANCELAMENTO_SOLICITADO,
            status_anterior=document.status,
            status_novo=document.status,
            descricao="Cancelamento fiscal solicitado.",
        )
        attempt = TentativaFiscal.objects.create(
            documento=document,
            operacao=TentativaFiscal.Operacao.CANCELAMENTO,
        )
        try:
            response = self.client.cancelar(
                document.tipo, document.acbr_id, justificativa
            )
        except ACBRAPIError as exc:
            self._finish_error(document, attempt, exc, mark_document_error=False)
            raise

        remote_status = self._remote_status(response.data, response.status_code)
        if remote_status != DocumentoFiscal.Status.CANCELADA:
            message = extract_safe_error(
                response.data,
                fallback="A ACBRAPI não confirmou o cancelamento do documento.",
            )
            error = ACBRAPIError(message, code="cancelamento_nao_confirmado")
            self._finish_error(document, attempt, error, mark_document_error=False)
            raise error

        document = self._apply_remote_response(
            document,
            response.data,
            http_status=response.status_code,
            operation=TentativaFiscal.Operacao.CANCELAMENTO,
        )
        self._finish_success(attempt, response)
        return document

    def baixar_xml(self, document):
        if document.status not in {
            DocumentoFiscal.Status.AUTORIZADA,
            DocumentoFiscal.Status.CANCELADA,
        }:
            raise FiscalConflictError("XML disponível apenas para documento autorizado ou cancelado.")
        return self._download(document, TentativaFiscal.Operacao.DOWNLOAD_XML)

    def baixar_pdf(self, document):
        if document.status != DocumentoFiscal.Status.AUTORIZADA:
            raise FiscalConflictError("PDF disponível apenas para documento autorizado.")
        return self._download(document, TentativaFiscal.Operacao.DOWNLOAD_PDF)

    def _download(self, document, operation):
        if not document.acbr_id:
            raise FiscalConflictError("O documento não possui identificador da ACBRAPI.")
        attempt = TentativaFiscal.objects.create(documento=document, operacao=operation)
        try:
            if operation == TentativaFiscal.Operacao.DOWNLOAD_XML:
                response = self.client.baixar_xml(document.acbr_id)
            else:
                response = self.client.baixar_pdf(document.tipo, document.acbr_id)
        except ACBRAPIError as exc:
            self._finish_error(document, attempt, exc, mark_document_error=False)
            raise
        self._finish_success(attempt, response)
        return response

    @staticmethod
    def _remote_status(data, http_status):
        raw_status = str(data.get("status") or "").strip().lower()
        mapped = REMOTE_STATUS_MAP.get(raw_status)
        if mapped:
            return mapped
        if http_status == 422:
            return DocumentoFiscal.Status.REJEITADA
        # Resposta 2xx sem status explícito nunca pode ser tratada como autorização.
        return DocumentoFiscal.Status.ERRO

    def _apply_remote_response(self, document, data, *, http_status, operation):
        new_status = self._remote_status(data, http_status)
        remote_id = self._remote_uuid(data.get("id"))
        now = timezone.now()

        with transaction.atomic():
            locked = DocumentoFiscal.all_objects.select_for_update().get(pk=document.pk)
            old_status = locked.status
            if remote_id:
                locked.acbr_id = remote_id
            locked.status = new_status
            locked.chave_acesso = self._safe_code(
                data.get("chave_acesso") or data.get("chave"), 44
            )
            locked.protocolo = self._safe_code(data.get("protocolo"), 50)
            locked.numero = self._safe_code(data.get("numero"), 20)
            locked.serie = self._safe_code(data.get("serie"), 5)
            locked.codigo_status = self._safe_code(
                data.get("codigo_status") or data.get("codigo"), 20
            )
            locked.mensagem_sefaz = extract_safe_error(data, fallback="")
            if new_status == DocumentoFiscal.Status.AUTORIZADA and not locked.autorizada_em:
                locked.autorizada_em = now
            if new_status == DocumentoFiscal.Status.CANCELADA and not locked.cancelada_em:
                locked.cancelada_em = now
            locked.save(
                update_fields=[
                    "acbr_id",
                    "status",
                    "chave_acesso",
                    "protocolo",
                    "numero",
                    "serie",
                    "codigo_status",
                    "mensagem_sefaz",
                    "autorizada_em",
                    "cancelada_em",
                    "updated_at",
                ]
            )
            if old_status != new_status:
                EventoFiscal.objects.create(
                    documento=locked,
                    tipo=EventoFiscal.Tipo.STATUS_ALTERADO,
                    status_anterior=old_status,
                    status_novo=new_status,
                    descricao=f"Status atualizado apó {operation.lower()}.",
                )
        return locked

    @staticmethod
    def _finish_success(attempt, response):
        status_remote = ""
        if hasattr(response, "data"):
            status_remote = sanitize_text(response.data.get("status", ""), max_length=30)
        TentativaFiscal.objects.filter(pk=attempt.pk).update(
            resultado=TentativaFiscal.Resultado.SUCESSO,
            http_status=getattr(response, "status_code", None),
            status_remoto=status_remote,
            finalizada_em=timezone.now(),
        )

    @staticmethod
    def _finish_error(document, attempt, error, *, mark_document_error):
        message = sanitize_text(getattr(error, "message", str(error)))
        TentativaFiscal.objects.filter(pk=attempt.pk).update(
            resultado=TentativaFiscal.Resultado.ERRO,
            http_status=getattr(error, "upstream_status", None),
            codigo_erro=sanitize_text(getattr(error, "code", "fiscal_error"), max_length=50),
            mensagem=message,
            finalizada_em=timezone.now(),
        )
        if mark_document_error:
            with transaction.atomic():
                locked = DocumentoFiscal.all_objects.select_for_update().get(pk=document.pk)
                old_status = locked.status
                locked.status = DocumentoFiscal.Status.ERRO
                locked.mensagem_sefaz = message
                locked.save(update_fields=["status", "mensagem_sefaz", "updated_at"])
                if old_status != locked.status:
                    EventoFiscal.objects.create(
                        documento=locked,
                        tipo=EventoFiscal.Tipo.STATUS_ALTERADO,
                        status_anterior=old_status,
                        status_novo=locked.status,
                        descricao="Falha de comunicação durante a emissão.",
                    )

    @staticmethod
    def _remote_uuid(value):
        if not value:
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return None

    @staticmethod
    def _safe_code(value, max_length):
        if value is None:
            return ""
        return re.sub(r"[^A-Za-z0-9.-]", "", str(value))[:max_length]

