import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.fiscal.crypto import decrypt_secret
from apps.fiscal.models import ConfiguracaoFiscal, InutilizacaoNumeracao


@pytest.mark.django_db
def test_salva_segredos_criptografados_sem_devolve_los(auth_client):
    response = auth_client.patch(
        "/api/fiscal/configuracao/",
        {
            "cnpj": "12345678000199",
            "uf": "ce",
            "api_key": "chave-geranet-secreta",
            "certificado_senha": "senha-certificado",
            "certificado": SimpleUploadedFile("empresa.pfx", b"certificado-teste"),
        },
        format="multipart",
    )

    assert response.status_code == 200
    assert "api_key" not in response.data
    assert "certificado_senha" not in response.data
    assert response.data["api_key_configurada"] is True
    assert response.data["certificado_configurado"] is True
    config = ConfiguracaoFiscal.atual()
    assert "chave-geranet-secreta" not in config.api_key_encrypted
    assert decrypt_secret(config.api_key_encrypted) == "chave-geranet-secreta"
    assert config.uf == "CE"


@pytest.mark.django_db
def test_configuracao_fiscal_exige_gestao(api_client, django_user_model):
    user = django_user_model.objects.create_user("caixa", password="teste123")
    api_client.force_authenticate(user=user)
    assert api_client.get("/api/fiscal/configuracao/").status_code == 403


@pytest.mark.django_db
def test_atualiza_configuracao_por_json_preservando_certificado_vazio(auth_client):
    response = auth_client.patch(
        "/api/fiscal/configuracao/",
        {
            "cnpj": "41.771.788/0001-17",
            "cep": "59575-000",
            "codigo_municipio": "2403608",
            "uf": "rn",
            "razao_social": "E S G DOS SANTOS",
            "certificado": {},
            "certificado_configurado": False,
            "updated_at": "2026-11-09T23:02:34-03:00",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["cnpj"] == "41771788000117"
    assert response.data["cep"] == "59575000"
    assert response.data["uf"] == "RN"


@pytest.mark.django_db
def test_validacao_informa_quais_campos_estao_pendentes(auth_client):
    config = ConfiguracaoFiscal.atual()
    config.razao_social = "Empresa Teste"
    config.save()

    response = auth_client.post("/api/fiscal/configuracao/validar/")

    assert response.status_code == 400
    assert "Certificado A1" in response.data["campos_pendentes"]
    assert "CNPJ" in response.data["campos_pendentes"]
    assert "Razão social" not in response.data["campos_pendentes"]


@pytest.mark.django_db
def test_inutilizacao_exige_gestao(api_client, django_user_model):
    user = django_user_model.objects.create_user("caixa-inutilizacao", password="teste123")
    api_client.force_authenticate(user=user)

    assert api_client.get("/api/fiscal/inutilizacoes/").status_code == 403


@pytest.mark.django_db
def test_solicita_inutilizacao_pelo_endpoint(auth_client, monkeypatch):
    def fake_inutilizar(self, **kwargs):
        return InutilizacaoNumeracao.objects.create(
            tipo=kwargs["tipo"],
            ambiente="homologacao",
            status="INUTILIZADA",
            serie=kwargs["serie"],
            ano=kwargs["ano"],
            numero_inicial=kwargs["numero_inicial"],
            numero_final=kwargs["numero_final"],
            justificativa=kwargs["justificativa"],
            codigo_status="102",
        )

    monkeypatch.setattr(
        "apps.fiscal.views.FiscalService.inutilizar_numeracao",
        fake_inutilizar,
    )

    response = auth_client.post(
        "/api/fiscal/inutilizacoes/",
        {
            "tipo": "NFCE",
            "serie": "2",
            "ano": 2026,
            "numero_inicial": 3,
            "numero_final": 3,
            "justificativa": "Numeração não utilizada no sistema.",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["status"] == "INUTILIZADA"
    assert response.data["codigo_status"] == "102"
