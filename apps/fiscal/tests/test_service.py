from decimal import Decimal
from datetime import timedelta
from types import SimpleNamespace

import pytest

from apps.fiscal.models import (
    CartaCorrecaoFiscal,
    ConfiguracaoFiscal,
    DocumentoFiscal,
    InutilizacaoNumeracao,
    TentativaFiscal,
)
from apps.fiscal.services.errors import FiscalConflictError
from apps.fiscal.services.errors import GeranetAPIError
from apps.fiscal.services.client import GeranetResponse
from apps.fiscal.services.fiscal import FiscalService
from apps.vendas.tests.factories import VendaFactory
from django.utils import timezone


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
    venda = VendaFactory(status="FINALIZADA", total=Decimal("10.00"))
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


@pytest.mark.django_db
def test_nao_reenvia_rejeitada_em_ambiente_diferente(monkeypatch):
    config = ConfiguracaoFiscal.atual()
    config.ambiente = "producao"
    config.save()
    venda = VendaFactory(status="FINALIZADA", total="10.00")
    DocumentoFiscal.objects.create(
        venda=venda,
        tipo="NFCE",
        status="REJEITADA",
        ambiente="homologacao",
        referencia=f"venda:{venda.id_externo}:nfce",
        numero="1",
        serie="2",
    )
    monkeypatch.setattr(
        "apps.fiscal.services.fiscal.VendaFiscalPayloadBuilder",
        lambda *args, **kwargs: pytest.fail("não deveria construir o payload"),
    )

    with pytest.raises(FiscalConflictError, match="outro ambiente fiscal"):
        FiscalService(client=SimpleNamespace()).emitir(venda=venda, tipo="NFCE")


@pytest.mark.django_db
def test_inutiliza_faixa_e_registra_retorno(monkeypatch, admin_user):
    config = ConfiguracaoFiscal.atual()
    config.ambiente = "homologacao"
    config.save()
    monkeypatch.setattr(
        "apps.fiscal.services.fiscal.InutilizacaoFiscalPayloadBuilder.build",
        lambda *args, **kwargs: {"acao": "inutilizarNumeracao"},
    )
    client = SimpleNamespace(
        inutilizar_numeracao=lambda payload: GeranetResponse(
            data={
                "situacao": "sucesso",
                "cstat": "102",
                "mensagem": "Inutilização de número homologado",
                "protocolo": "123456789",
            },
            status_code=200,
        )
    )

    record = FiscalService(client=client).inutilizar_numeracao(
        tipo="NFCE",
        serie="2",
        ano=2026,
        numero_inicial=3,
        numero_final=4,
        justificativa="Numeração não utilizada no sistema.",
        usuario=admin_user,
    )

    assert record.status == InutilizacaoNumeracao.Status.INUTILIZADA
    assert record.codigo_status == "102"
    assert record.ambiente == "homologacao"
    assert record.solicitada_por == admin_user


@pytest.mark.django_db
def test_nao_inutiliza_numero_autorizado():
    config = ConfiguracaoFiscal.atual()
    config.ambiente = "producao"
    config.save()
    venda = VendaFactory(status="FINALIZADA", total="10.00")
    DocumentoFiscal.objects.create(
        venda=venda,
        tipo="NFCE",
        status="AUTORIZADA",
        ambiente="producao",
        referencia=f"venda:{venda.id_externo}:nfce",
        numero="2",
        serie="2",
    )

    with pytest.raises(FiscalConflictError, match="número autorizado"):
        FiscalService(client=SimpleNamespace()).inutilizar_numeracao(
            tipo="NFCE",
            serie="2",
            ano=2026,
            numero_inicial=1,
            numero_final=3,
            justificativa="Numeração não utilizada no sistema.",
        )


@pytest.mark.django_db
def test_timeout_de_emissao_marca_resultado_indefinido(monkeypatch):
    venda = VendaFactory(status="FINALIZADA", total=Decimal("10.00"))
    FakeBuilder.calls = []
    monkeypatch.setattr("apps.fiscal.services.fiscal.VendaFiscalPayloadBuilder", FakeBuilder)
    client = SimpleNamespace(
        emitir=lambda payload: (_ for _ in ()).throw(
            GeranetAPIError(
                "Tempo limite excedido.",
                code="geranet_timeout",
                http_status=504,
            )
        )
    )

    with pytest.raises(GeranetAPIError):
        FiscalService(client=client).emitir(venda=venda, tipo="NFCE")

    document = DocumentoFiscal.all_objects.get(venda=venda, tipo="NFCE")
    assert document.status == DocumentoFiscal.Status.INDEFINIDO
    assert "Tempo limite" in document.mensagem_sefaz


class CorrectionBuilder:
    def __init__(self, *args, **kwargs):
        pass

    def build_correction(self, document, **kwargs):
        return {"acao": "cartaCorrecao", **kwargs}


@pytest.mark.django_db
def test_registra_carta_correcao_da_nfe(monkeypatch, admin_user):
    ConfiguracaoFiscal.atual()
    venda = VendaFactory(status="FINALIZADA", total="10.00")
    document = DocumentoFiscal.objects.create(
        venda=venda,
        tipo="NFE",
        status="AUTORIZADA",
        ambiente="homologacao",
        referencia=f"venda:{venda.id_externo}:nfe",
        numero="1",
        serie="2",
        chave_acesso="1" * 44,
    )
    monkeypatch.setattr(
        "apps.fiscal.services.fiscal.VendaFiscalPayloadBuilder",
        CorrectionBuilder,
    )
    client = SimpleNamespace(
        carta_correcao=lambda payload: GeranetResponse(
            data={
                "situacao": "sucesso",
                "cstat": "135",
                "mensagem": "Evento registrado e vinculado a NF-e",
                "protocolo": "123456789",
            },
            status_code=200,
        )
    )

    record = FiscalService(client=client).carta_correcao(
        document,
        texto_correcao="Correção da informação complementar da nota.",
        usuario=admin_user,
    )

    assert record.status == CartaCorrecaoFiscal.Status.REGISTRADA
    assert record.sequencia == 1
    assert record.protocolo == "123456789"


@pytest.mark.django_db
def test_bloqueia_cancelamento_nfce_fora_do_prazo_do_rn():
    config = ConfiguracaoFiscal.atual()
    config.uf = "RN"
    config.save()
    venda = VendaFactory(status="FINALIZADA", total="10.00")
    document = DocumentoFiscal.objects.create(
        venda=venda,
        tipo="NFCE",
        status="AUTORIZADA",
        ambiente="homologacao",
        referencia=f"venda:{venda.id_externo}:nfce",
        numero="1",
        serie="2",
        chave_acesso="1" * 44,
        protocolo="123",
        autorizada_em=timezone.now() - timedelta(minutes=31),
    )

    can_cancel, _deadline, reason = FiscalService.cancellation_state(document, config)

    assert can_cancel is False
    assert "30 minutos" in reason
