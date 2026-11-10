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
    assert r"^api/health/$" in settings.SECURE_REDIRECT_EXEMPT


def test_fiscal_settings_use_geranet(monkeypatch):
    monkeypatch.setenv("GERANET_API_URL", "https://nfe.geranet.net/api/v1")
    monkeypatch.setenv("FISCAL_TIMEOUT_SECONDS", "45")

    from config.settings import base

    settings = importlib.reload(base)

    assert settings.GERANET_API_URL == "https://nfe.geranet.net/api/v1"
    assert settings.GERANET_TIMEOUT == 45
