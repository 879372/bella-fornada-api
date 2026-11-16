import base64
import io
import zipfile
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
import requests

from apps.fiscal.models import ConfiguracaoFiscal, DocumentoFiscal
from apps.vendas.tests.factories import VendaFactory


@pytest.fixture
def configured(settings, monkeypatch):
    settings.RESEND_API_KEY = 're_test_only'
    config = ConfiguracaoFiscal.atual()
    config.ambiente = 'producao'
    config.email_contador = 'contador@example.com'
    config.email_remetente = 'fiscal@kaibez.com.br'
    config.save()
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=200, ok=True, json=lambda: {'id': 'resend-test-123'})

    monkeypatch.setattr('apps.fiscal.services.contador.requests.post', post)
    return config, calls


def invoice(status='AUTORIZADA', environment='producao', created='2026-11-16T12:00:00-03:00', xml=b'<nfeProc>original</nfeProc>'):
    doc = DocumentoFiscal.objects.create(
        venda=VendaFactory(status='FINALIZADA'), tipo='NFCE', status=status,
        ambiente=environment, referencia=str(uuid4()), numero='123', serie='1', xml_conteudo=xml,
    )
    DocumentoFiscal.objects.filter(pk=doc.pk).update(created_at=datetime.fromisoformat(created))
    return doc


def send(client, **overrides):
    return client.post('/api/fiscal/documentos/enviar-xml-contador/', {
        'data_inicio': '2026-11-01', 'data_fim': '2026-11-30', **overrides,
    }, format='json')


@pytest.mark.django_db
def test_sends_original_xmls_in_zip_all_pages_local_date_boundaries_and_environment(auth_client, configured):
    _, calls = configured
    invoice(created='2026-11-01T00:00:00-03:00', xml=b'<nfeProc>primeira</nfeProc>')
    invoice(status='CANCELADA', created='2026-11-30T23:59:59.999999-03:00', xml=b'<nfeProc>cancelada</nfeProc>')
    for number in range(49):
        invoice(xml=f'<nfeProc>nota-{number}</nfeProc>'.encode())
    invoice(status='REJEITADA')
    invoice(environment='homologacao')
    invoice(created='2026-12-01T00:00:00-03:00')
    invoice(created='2026-10-31T23:59:59.999999-03:00')
    invoice().soft_delete()

    response = send(auth_client)
    assert response.status_code == 200
    assert response.data['quantidade'] == 51
    assert response.data['email'] == 'contador@example.com'
    assert len(calls) == 1
    url, request = calls[0]
    assert url == 'https://api.resend.com/emails'
    assert request['headers']['Authorization'] == 'Bearer re_test_only'
    assert request['timeout'] == (5, 30)
    payload = request['json']
    assert payload['to'] == ['contador@example.com']
    attachment = payload['attachments'][0]
    assert attachment['filename'].endswith('-producao.zip')
    assert attachment['content_type'] == 'application/zip'
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(attachment['content']))) as archive:
        assert len(archive.namelist()) == 51
        contents = {archive.read(name) for name in archive.namelist()}
        assert b'<nfeProc>primeira</nfeProc>' in contents
        assert b'<nfeProc>cancelada</nfeProc>' in contents
        assert b'<nfeProc>original</nfeProc>' not in contents
    assert 're_test_only' not in str(response.data)


@pytest.mark.django_db
def test_recipient_override_does_not_change_default_and_retry_has_stable_idempotency(auth_client, configured):
    config, calls = configured
    invoice()
    first = send(auth_client, email='outro@example.com')
    second = send(auth_client, email='outro@example.com')
    assert first.status_code == second.status_code == 200
    assert calls[0][1]['headers']['Idempotency-Key'] == calls[1][1]['headers']['Idempotency-Key']
    assert calls[0][1]['json'] == calls[1][1]['json']
    config.refresh_from_db()
    assert config.email_contador == 'contador@example.com'
    send(auth_client)
    assert calls[2][1]['headers']['Idempotency-Key'] != calls[1][1]['headers']['Idempotency-Key']


@pytest.mark.django_db
def test_invalid_period_email_empty_selection_and_missing_xml_do_not_send(auth_client, configured):
    _, calls = configured
    assert send(auth_client, data_inicio='2026-12-01').status_code == 400
    assert send(auth_client, email='invalido').status_code == 400
    assert send(auth_client).status_code == 400
    invoice(xml=None)
    response = send(auth_client)
    assert response.status_code == 409
    assert 'sem XML' in response.data['detail']
    assert calls == []


@pytest.mark.django_db
def test_zip_size_limit_and_missing_key_do_not_send(auth_client, configured, monkeypatch, settings):
    _, calls = configured
    invoice()
    monkeypatch.setattr('apps.fiscal.services.contador.MAX_ZIP_BYTES', 10)
    assert send(auth_client).status_code == 400
    settings.RESEND_API_KEY = ''
    assert send(auth_client).status_code == 503
    assert calls == []


@pytest.mark.django_db
@pytest.mark.parametrize('kind,expected', [('timeout', 504), ('connection', 503), (401, 503), (403, 503), (429, 503), (500, 502), ('bad_json', 502)])
def test_provider_errors_are_safe(auth_client, configured, monkeypatch, kind, expected):
    invoice()

    def failure(*args, **kwargs):
        if kind == 'timeout':
            raise requests.Timeout('sensitive provider internals')
        if kind == 'connection':
            raise requests.ConnectionError('sensitive provider internals')
        if kind == 'bad_json':
            return SimpleNamespace(status_code=200, ok=True, json=lambda: {})
        return SimpleNamespace(status_code=kind, ok=False)

    monkeypatch.setattr('apps.fiscal.services.contador.requests.post', failure)
    response = send(auth_client)
    assert response.status_code == expected
    assert 'sensitive' not in str(response.data)
    assert 're_test_only' not in str(response.data)


@pytest.mark.django_db
def test_only_management_can_send(api_client, django_user_model, configured):
    _, calls = configured
    assert send(api_client).status_code == 401
    api_client.force_authenticate(user=django_user_model.objects.create_user('caixa-envio'))
    assert send(api_client).status_code == 403
    assert calls == []


@pytest.mark.django_db
def test_configuration_persists_email_and_never_exposes_resend_key(auth_client, configured):
    response = auth_client.patch('/api/fiscal/configuracao/', {'email_contador': 'novo@example.com'}, format='json')
    assert response.status_code == 200
    assert response.data['email_contador'] == 'novo@example.com'
    assert response.data['resend_configurado'] is True
    assert 're_test_only' not in str(response.data)
    assert auth_client.patch('/api/fiscal/configuracao/', {'email_contador': 'invalido'}, format='json').status_code == 400
