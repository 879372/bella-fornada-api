from types import SimpleNamespace

import pytest

from apps.fiscal.models import ConfiguracaoFiscal, DocumentoFiscal, TentativaFiscal
from apps.fiscal.services.client import GeranetResponse
from apps.fiscal.services.fiscal import FiscalService
from apps.vendas.tests.factories import VendaFactory


class SuccessfulClient:
    def __init__(self):
        self.payloads = []

    def emitir(self, payload):
        self.payloads.append(payload)
        return GeranetResponse(
            data={
                "situacao": "sucesso",
                "cstat": "100",
                "mensagem": "Autorizado o uso da NF-e",
                "chave": "1" * 44,
                "protocolo": "123456789",
            },
            status_code=200,
        )


class FakeBuilder:
    calls = []

    def __init__(self, venda, **kwargs):
        self.__class__.calls.append((venda, kwargs))

    def build(self):
        return {"acao": "emitir"}


@pytest.mark.django_db
def test_reenvia_documento_rejeitado_com_mesmo_numero(monkeypatch, admin_user):
    config = ConfiguracaoFiscal.atual()
    config.proximo_numero_nfce = 8
    config.save()
    venda = VendaFactory(status="FINALIZADA", total="10.00")
    document = DocumentoFiscal.objects.create(
        venda=venda,
        tipo="NFCE",
        status="REJEITADA",
        ambiente="homologacao",
        referencia=f"venda:{venda.id_externo}:nfce",
        numero="7",
        serie="2",
        codigo_status="878",
        mensagem_sefaz="URL de consulta inválida",
    )
    client = SuccessfulClient()
    FakeBuilder.calls = []
    monkeypatch.setattr("apps.fiscal.services.fiscal.VendaFiscalPayloadBuilder", FakeBuilder)

    result, created = FiscalService(client=client).emitir(
        venda=venda,
        tipo="NFCE",
        usuario=admin_user,
    )

    config.refresh_from_db()
    assert created is False
    assert result.pk == document.pk
    assert result.status == DocumentoFiscal.Status.AUTORIZADA
    assert result.numero == "7"
    assert config.proximo_numero_nfce == 8
    assert FakeBuilder.calls[0][1]["numero"] == "7"
    assert len(client.payloads) == 1
    assert TentativaFiscal.objects.filter(documento=document).count() == 1


@pytest.mark.django_db
def test_documento_autorizado_continua_idempotente(monkeypatch):
    venda = VendaFactory(status="FINALIZADA", total="10.00")
    document = DocumentoFiscal.objects.create(
        venda=venda,
        tipo="NFE",
        status="AUTORIZADA",
        ambiente="homologacao",
        referencia=f"venda:{venda.id_externo}:nfe",
        numero="3",
        serie="2",
    )
    client = SimpleNamespace(emitir=lambda payload: pytest.fail("não deveria transmitir"))
    monkeypatch.setattr(
        "apps.fiscal.services.fiscal.VendaFiscalPayloadBuilder",
        lambda *args, **kwargs: pytest.fail("não deveria reconstruir o payload"),
    )

    result, created = FiscalService(client=client).emitir(venda=venda, tipo="NFE")

    assert created is False
    assert result.pk == document.pk
