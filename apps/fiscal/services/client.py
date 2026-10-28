import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import requests
from django.conf import settings

from .errors import ACBRAPIError, FiscalConfigurationError
from .security import extract_safe_error, sanitize_text


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ACBRJSONResponse:
    data: dict
    status_code: int


@dataclass(frozen=True)
class ACBRBinaryResponse:
    content: bytes
    content_type: str
    status_code: int


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class ACBRAPIClient:
    """Cliente B2B da ACBRAPI interna, autenticado exclusivamente por X-Api-Key."""

    def __init__(self, *, session=None, base_url=None, api_key=None, timeout=None):
        self.base_url = (base_url or getattr(settings, "ACBR_API_URL", "")).strip().rstrip("/")
        self.api_key = (api_key or getattr(settings, "ACBR_API_KEY", "")).strip()
        read_timeout = timeout or getattr(settings, "ACBR_API_TIMEOUT", 30)
        connect_timeout = getattr(settings, "ACBR_API_CONNECT_TIMEOUT", 5)
        self.timeout = (float(connect_timeout), float(read_timeout))
        self.max_download_bytes = int(
            getattr(settings, "ACBR_API_MAX_DOWNLOAD_BYTES", 10 * 1024 * 1024)
        )
        self.session = session or requests.Session()

        if not self.base_url:
            raise FiscalConfigurationError("ACBR_API_URL não foi configurada.")
        if not self.api_key:
            raise FiscalConfigurationError("ACBR_API_KEY não foi configurada.")
        if not self.base_url.startswith(("http://", "https://")):
            raise FiscalConfigurationError("ACBR_API_URL deve ser uma URL HTTP(S) válida.")

    @property
    def headers(self):
        return {
            "X-Api-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request_json(self, method, path, *, payload=None, accepted_statuses=()):
        url = f"{self.base_url}/{path.lstrip('/')}"
        logger.info("ACBRAPI request %s %s", method.upper(), path)
        try:
            response = self.session.request(
                method,
                url,
                json=_json_safe(payload) if payload is not None else None,
                headers=self.headers,
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            logger.warning("Timeout na ACBRAPI em %s %s", method.upper(), path)
            raise ACBRAPIError(
                "A ACBRAPI não respondeu dentro do tempo limite.",
                code="acbr_timeout",
                http_status=504,
            ) from exc
        except requests.ConnectionError as exc:
            logger.warning("ACBRAPI indisponível em %s %s", method.upper(), path)
            raise ACBRAPIError(
                "Não foi possível conectar à ACBRAPI.",
                code="acbr_unavailable",
                http_status=503,
            ) from exc
        except requests.RequestException as exc:
            logger.exception("Falha de transporte na ACBRAPI em %s %s", method.upper(), path)
            raise ACBRAPIError("Falha de transporte na comunicação com a ACBRAPI.") from exc

        data = self._parse_json(response)
        if not response.ok and response.status_code not in accepted_statuses:
            message = extract_safe_error(data)
            logger.warning(
                "ACBRAPI retornou HTTP %s em %s %s: %s",
                response.status_code,
                method.upper(),
                path,
                message,
            )
            raise ACBRAPIError(
                message,
                code="acbr_http_error",
                upstream_status=response.status_code,
            )
        return ACBRJSONResponse(data=data, status_code=response.status_code)

    def _request_binary(self, path, *, expected_types):
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = dict(self.headers)
        headers["Accept"] = ", ".join(expected_types)
        headers.pop("Content-Type", None)
        logger.info("ACBRAPI download GET %s", path)
        try:
            response = self.session.request(
                "GET",
                url,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise ACBRAPIError(
                "A ACBRAPI não respondeu ao baixar o documento.",
                code="acbr_timeout",
                http_status=504,
            ) from exc
        except requests.ConnectionError as exc:
            raise ACBRAPIError(
                "Não foi possível conectar à ACBRAPI.",
                code="acbr_unavailable",
                http_status=503,
            ) from exc
        except requests.RequestException as exc:
            raise ACBRAPIError("Falha ao baixar o documento fiscal.") from exc

        if not response.ok:
            data = self._parse_json(response, required=False)
            raise ACBRAPIError(
                extract_safe_error(data, fallback="Documento fiscal não disponível."),
                code="acbr_download_error",
                upstream_status=response.status_code,
            )

        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type not in expected_types:
            raise ACBRAPIError(
                "A ACBRAPI retornou um formato de arquivo inesperado.",
                code="acbr_invalid_content_type",
            )
        content = response.content
        if len(content) > self.max_download_bytes:
            raise ACBRAPIError(
                "O documento retornado pela ACBRAPI excede o limite permitido.",
                code="acbr_download_too_large",
            )
        return ACBRBinaryResponse(content, content_type, response.status_code)

    @staticmethod
    def _parse_json(response, *, required=True):
        try:
            data = response.json()
        except ValueError as exc:
            if not required:
                return {}
            raise ACBRAPIError(
                "A ACBRAPI retornou uma resposta inválida.",
                code="acbr_invalid_response",
            ) from exc
        if not isinstance(data, dict):
            if not required:
                return {}
            raise ACBRAPIError(
                "A ACBRAPI retornou uma resposta inválida.",
                code="acbr_invalid_response",
            )
        return data

    def emitir(self, tipo, payload):
        endpoint = "nfce/emitir/" if tipo == "NFCE" else "nfe/emitir/"
        # 422 representa uma rejeição fiscal válida, não falha de transporte.
        return self._request_json("POST", endpoint, payload=payload, accepted_statuses=(422,))

    def consultar_nota(self, acbr_id):
        return self._request_json("GET", f"notas/{acbr_id}/")

    def cancelar(self, tipo, acbr_id, justificativa):
        tipo_path = "nfce" if tipo == "NFCE" else "nfe"
        return self._request_json(
            "POST",
            f"{tipo_path}/{acbr_id}/cancelar/",
            payload={"justificativa": sanitize_text(justificativa, max_length=255)},
            accepted_statuses=(422,),
        )

    def baixar_xml(self, acbr_id):
        return self._request_binary(
            f"notas/{acbr_id}/xml/",
            expected_types=("application/xml", "text/xml"),
        )

    def baixar_pdf(self, tipo, acbr_id):
        if tipo == "NFCE":
            path = f"nfce/{acbr_id}/danfce/"
        else:
            path = f"nfe/{acbr_id}/danfe/"
        return self._request_binary(path, expected_types=("application/pdf",))

