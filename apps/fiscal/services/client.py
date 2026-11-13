import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import requests
from django.conf import settings

from apps.fiscal.crypto import decrypt_secret

from .errors import FiscalConfigurationError, GeranetAPIError
from .security import extract_safe_error

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeranetResponse:
    data: dict
    status_code: int


@dataclass(frozen=True)
class FiscalBinaryResponse:
    content: bytes
    content_type: str
    status_code: int = 200


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


class GeranetClient:
    """Cliente da API fiscal Geranet, autenticado por Bearer token."""

    def __init__(self, configuracao, *, session=None, timeout=None):
        self.base_url = (configuracao.api_url or settings.GERANET_API_URL).strip().rstrip("/")
        self.api_key = decrypt_secret(configuracao.api_key_encrypted).strip()
        self.timeout = (5.0, float(timeout or settings.GERANET_TIMEOUT))
        self.session = session or requests.Session()
        if not self.base_url.startswith(("http://", "https://")):
            raise FiscalConfigurationError("A URL da API Geranet é inválida.")
        if not self.api_key:
            raise FiscalConfigurationError("Informe a chave da API Geranet na configuração fiscal.")

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _post(self, path, payload):
        url = f"{self.base_url}/{path.lstrip('/')}"
        logger.info("Geranet request POST %s", path)
        try:
            response = self.session.post(
                url, json=_json_safe(payload), headers=self.headers, timeout=self.timeout
            )
        except requests.Timeout as exc:
            raise GeranetAPIError(
                "A Geranet não respondeu dentro do tempo limite.",
                code="geranet_timeout", http_status=504,
            ) from exc
        except requests.ConnectionError as exc:
            raise GeranetAPIError(
                "Não foi possível conectar à Geranet.",
                code="geranet_indisponivel", http_status=503,
            ) from exc
        except requests.RequestException as exc:
            raise GeranetAPIError("Falha na comunicação com a Geranet.") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise GeranetAPIError(
                "A Geranet retornou uma resposta inválida.", code="geranet_resposta_invalida"
            ) from exc
        if not isinstance(data, dict):
            raise GeranetAPIError(
                "A Geranet retornou uma resposta inválida.", code="geranet_resposta_invalida"
            )
        if not response.ok and response.status_code != 422:
            raise GeranetAPIError(
                extract_safe_error(data, fallback="Falha na API fiscal Geranet."),
                code="geranet_http_error", upstream_status=response.status_code,
            )
        return GeranetResponse(data=data, status_code=response.status_code)

    def emitir(self, payload):
        return self._post("nfe/emitir", payload)

    def cancelar(self, payload):
        return self._post("nfe/cancelar", payload)

    def inutilizar_numeracao(self, payload):
        return self._post("nfe/inutilizar-numeracao", payload)

    def carta_correcao(self, payload):
        return self._post("nfe/carta-correcao", payload)
