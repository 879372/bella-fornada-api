import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.fiscal.crypto import decrypt_secret
from apps.fiscal.models import ConfiguracaoFiscal


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
