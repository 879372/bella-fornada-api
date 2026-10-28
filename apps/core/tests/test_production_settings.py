import importlib


def test_production_settings_include_railway_and_frontend(monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", "localhost")
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "api.example.up.railway.app")
    monkeypatch.setenv("RAILWAY_PRIVATE_DOMAIN", "api.railway.internal")
    monkeypatch.setenv("FRONTEND_PUBLIC_URL", "https://bella.example.com/")
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("CSRF_TRUSTED_ORIGINS", raising=False)

    from config.settings import production

    settings = importlib.reload(production)

    assert "api.example.up.railway.app" in settings.ALLOWED_HOSTS
    assert "api.railway.internal" in settings.ALLOWED_HOSTS
    assert "https://bella.example.com" in settings.CORS_ALLOWED_ORIGINS
    assert "https://bella.example.com" in settings.CSRF_TRUSTED_ORIGINS


def test_fiscal_settings_accept_legacy_railway_names(monkeypatch):
    monkeypatch.delenv("ACBR_API_URL", raising=False)
    monkeypatch.delenv("ACBR_API_KEY", raising=False)
    monkeypatch.delenv("FISCAL_CNPJ_EMITENTE", raising=False)
    monkeypatch.setenv("FISCAL_API_URL", "https://fiscal.example.com/api/fiscal")
    monkeypatch.setenv("FISCAL_API_KEY", "secret-test-key")
    monkeypatch.setenv("EMPRESA_CNPJ", "12345678000199")

    from config.settings import base

    settings = importlib.reload(base)

    assert settings.ACBR_API_URL == "https://fiscal.example.com/api/fiscal"
    assert settings.ACBR_API_KEY == "secret-test-key"
    assert settings.FISCAL_CNPJ_EMITENTE == "12345678000199"
