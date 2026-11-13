from types import SimpleNamespace

from apps.fiscal.crypto import encrypt_secret
from apps.fiscal.services.client import GeranetClient


class Response:
    ok = True
    status_code = 200
    def json(self):
        return {"situacao": "sucesso", "cstat": "100"}


class Session:
    def post(self, url, **kwargs):
        self.url, self.kwargs = url, kwargs
        return Response()


def test_client_uses_bearer_and_official_emission_route(settings):
    settings.GERANET_TIMEOUT = 30
    session = Session()
    config = SimpleNamespace(api_url="https://nfe.geranet.net/api/v1", api_key_encrypted=encrypt_secret("secret"))
    GeranetClient(config, session=session).emitir({"acao": "emitir"})
    assert session.url.endswith("/api/v1/nfe/emitir")
    assert session.kwargs["headers"]["Authorization"] == "Bearer secret"


def test_client_uses_official_number_invalidation_route(settings):
    settings.GERANET_TIMEOUT = 30
    session = Session()
    config = SimpleNamespace(
        api_url="https://nfe.geranet.net/api/v1",
        api_key_encrypted=encrypt_secret("secret"),
    )

    GeranetClient(config, session=session).inutilizar_numeracao(
        {"acao": "inutilizarNumeracao"}
    )

    assert session.url.endswith("/api/v1/nfe/inutilizar-numeracao")


def test_client_uses_official_correction_letter_route(settings):
    settings.GERANET_TIMEOUT = 30
    session = Session()
    config = SimpleNamespace(
        api_url="https://nfe.geranet.net/api/v1",
        api_key_encrypted=encrypt_secret("secret"),
    )

    GeranetClient(config, session=session).carta_correcao({"acao": "cartaCorrecao"})

    assert session.url.endswith("/api/v1/nfe/carta-correcao")
