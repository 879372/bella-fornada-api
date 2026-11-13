import base64
from datetime import timedelta

from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from django.db.models import Count, Exists, OuterRef
from django.utils import timezone

from apps.fiscal.crypto import decrypt_secret
from apps.fiscal.models import ConfiguracaoFiscal, DocumentoFiscal
from apps.vendas.models import Venda


class FiscalMonitorService:
    CERTIFICATE_WARNING_DAYS = 30
    PROCESSING_WARNING_MINUTES = 5

    @classmethod
    def build(cls):
        config = ConfiguracaoFiscal.atual()
        documents = DocumentoFiscal.all_objects.filter(ambiente=config.ambiente)
        counts = {
            row["status"]: row["total"]
            for row in documents.values("status").annotate(total=Count("id"))
        }
        stale_processing = documents.filter(
            status=DocumentoFiscal.Status.PROCESSANDO,
            updated_at__lt=timezone.now()
            - timedelta(minutes=cls.PROCESSING_WARNING_MINUTES),
        ).count()
        any_document = DocumentoFiscal.all_objects.filter(
            venda_id=OuterRef("pk"), ambiente=config.ambiente
        )
        sales_without_document = (
            Venda.objects.filter(status="FINALIZADA")
            .annotate(has_document=Exists(any_document))
            .filter(has_document=False)
            .count()
        )
        certificate = cls._certificate_status(config)
        missing_config = cls._missing_configuration(config)
        alerts = []

        if missing_config:
            alerts.append(
                {
                    "nivel": "ERRO",
                    "codigo": "CONFIGURACAO_INCOMPLETA",
                    "titulo": "Configuração fiscal incompleta",
                    "descricao": "Campos pendentes: " + ", ".join(missing_config) + ".",
                    "quantidade": len(missing_config),
                }
            )
        if certificate["status"] in {"AUSENTE", "INVALIDO", "VENCIDO"}:
            alerts.append(
                {
                    "nivel": "ERRO",
                    "codigo": "CERTIFICADO_INVALIDO",
                    "titulo": "Certificado A1 indisponível",
                    "descricao": certificate["mensagem"],
                    "quantidade": 1,
                }
            )
        elif certificate["status"] == "VENCENDO":
            alerts.append(
                {
                    "nivel": "AVISO",
                    "codigo": "CERTIFICADO_VENCENDO",
                    "titulo": "Certificado A1 próximo do vencimento",
                    "descricao": certificate["mensagem"],
                    "quantidade": 1,
                }
            )

        cls._append_count_alert(
            alerts,
            counts.get(DocumentoFiscal.Status.INDEFINIDO, 0),
            "ERRO",
            "RESULTADO_INDEFINIDO",
            "Documento com resultado indefinido",
            "Não reenvie antes de confirmar a situação fiscal com a SEFAZ ou a Geranet.",
        )
        cls._append_count_alert(
            alerts,
            counts.get(DocumentoFiscal.Status.REJEITADA, 0),
            "AVISO",
            "DOCUMENTO_REJEITADO",
            "Documento fiscal rejeitado",
            "Corrija a causa indicada e use o reenvio com o mesmo número.",
        )
        cls._append_count_alert(
            alerts,
            counts.get(DocumentoFiscal.Status.ERRO, 0),
            "ERRO",
            "ERRO_FISCAL",
            "Erro de integração fiscal",
            "Revise a mensagem da tentativa antes de uma nova ação.",
        )
        cls._append_count_alert(
            alerts,
            stale_processing,
            "ERRO",
            "PROCESSAMENTO_ATRASADO",
            "Documento preso em processamento",
            f"A emissão está em processamento há mais de {cls.PROCESSING_WARNING_MINUTES} minutos.",
        )
        cls._append_count_alert(
            alerts,
            sales_without_document,
            "INFO",
            "VENDAS_SEM_DOCUMENTO",
            "Venda finalizada sem documento fiscal",
            "Confira se a venda precisa emitir NFC-e ou NF-e.",
        )
        alerts.append(
            {
                "nivel": "AVISO",
                "codigo": "CONTINGENCIA_NAO_SUPORTADA",
                "titulo": "Contingência offline ainda não disponível",
                "descricao": (
                    "A API pública da Geranet não documenta emissão NFC-e em contingência. "
                    "Em queda da integração, não faça reenvio repetido."
                ),
                "quantidade": 1,
            }
        )

        return {
            "ambiente": config.ambiente,
            "atualizado_em": timezone.now(),
            "certificado": certificate,
            "resumo": {
                "autorizadas": counts.get(DocumentoFiscal.Status.AUTORIZADA, 0),
                "canceladas": counts.get(DocumentoFiscal.Status.CANCELADA, 0),
                "rejeitadas": counts.get(DocumentoFiscal.Status.REJEITADA, 0),
                "indefinidas": counts.get(DocumentoFiscal.Status.INDEFINIDO, 0),
                "erros": counts.get(DocumentoFiscal.Status.ERRO, 0),
                "processando_atrasadas": stale_processing,
                "vendas_sem_documento": sales_without_document,
            },
            "contingencia": {
                "suportada": False,
                "provedor": "Geranet",
                "motivo": "Recurso ausente na documentação pública da API.",
            },
            "alertas": alerts,
        }

    @classmethod
    def _certificate_status(cls, config):
        if not config.certificado_encrypted:
            return {
                "status": "AUSENTE",
                "valido_ate": None,
                "dias_restantes": None,
                "mensagem": "O certificado A1 ainda não foi configurado.",
            }
        try:
            raw = base64.b64decode(
                decrypt_secret(config.certificado_encrypted), validate=True
            )
            password = decrypt_secret(config.certificado_senha_encrypted).encode() or None
            _key, certificate, _chain = load_key_and_certificates(raw, password)
            if not certificate:
                raise ValueError("Certificado ausente")
            expires_at = certificate.not_valid_after_utc
            remaining = (expires_at - timezone.now()).days
            if remaining < 0:
                status = "VENCIDO"
                message = f"O certificado A1 venceu em {expires_at.date().isoformat()}."
            elif remaining <= cls.CERTIFICATE_WARNING_DAYS:
                status = "VENCENDO"
                message = f"O certificado A1 vence em {remaining} dias."
            else:
                status = "VALIDO"
                message = f"Certificado válido por mais {remaining} dias."
            return {
                "status": status,
                "valido_ate": expires_at,
                "dias_restantes": remaining,
                "mensagem": message,
            }
        except Exception:
            return {
                "status": "INVALIDO",
                "valido_ate": None,
                "dias_restantes": None,
                "mensagem": "Não foi possível abrir o certificado A1 com a senha configurada.",
            }

    @staticmethod
    def _missing_configuration(config):
        required = {
            "Chave da API": config.api_key_encrypted,
            "Certificado A1": config.certificado_encrypted,
            "Senha do certificado": config.certificado_senha_encrypted,
            "CNPJ": config.cnpj,
            "Inscrição Estadual": config.inscricao_estadual,
            "Razão social": config.razao_social,
            "Endereço": config.logradouro,
            "Código IBGE": config.codigo_municipio,
            "UF": config.uf,
            "CEP": config.cep,
        }
        return [label for label, value in required.items() if not value]

    @staticmethod
    def _append_count_alert(
        alerts, count, level, code, title, description
    ):
        if count:
            alerts.append(
                {
                    "nivel": level,
                    "codigo": code,
                    "titulo": title,
                    "descricao": description,
                    "quantidade": count,
                }
            )
