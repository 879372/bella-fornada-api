import pytest

from apps.fiscal.models import ConfiguracaoFiscal, DocumentoFiscal
from apps.fiscal.services.monitor import FiscalMonitorService
from apps.vendas.tests.factories import VendaFactory


@pytest.mark.django_db
def test_monitor_destaca_resultado_indefinido_e_certificado_ausente():
    config = ConfiguracaoFiscal.atual()
    config.ambiente = "homologacao"
    config.save()
    venda = VendaFactory(status="FINALIZADA", total="10.00")
    DocumentoFiscal.objects.create(
        venda=venda,
        tipo="NFCE",
        status="INDEFINIDO",
        ambiente="homologacao",
        referencia=f"venda:{venda.id_externo}:nfce",
        numero="1",
        serie="2",
    )

    result = FiscalMonitorService.build()

    assert result["resumo"]["indefinidas"] == 1
    alert_codes = {alert["codigo"] for alert in result["alertas"]}
    assert "RESULTADO_INDEFINIDO" in alert_codes
    assert "CERTIFICADO_INVALIDO" in alert_codes
    assert result["contingencia"]["suportada"] is False
