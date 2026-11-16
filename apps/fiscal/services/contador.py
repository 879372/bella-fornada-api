import base64
import hashlib
import io
import json
import logging
import re
import zipfile
from datetime import datetime, time
from email.utils import formataddr

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

from apps.fiscal.models import ConfiguracaoFiscal, DocumentoFiscal
from .errors import FiscalConfigurationError, FiscalError, FiscalValidationError

logger = logging.getLogger(__name__)
MAX_ZIP_BYTES = 20 * 1024 * 1024


def compactar_xmls(config, inicio, fim):
    tz = timezone.get_current_timezone()
    documents = DocumentoFiscal.objects.filter(
        ambiente=config.ambiente,
        status__in=[DocumentoFiscal.Status.AUTORIZADA, DocumentoFiscal.Status.CANCELADA],
        created_at__gte=timezone.make_aware(datetime.combine(inicio, time.min), tz),
        created_at__lte=timezone.make_aware(datetime.combine(fim, time.max), tz),
    ).only('id', 'id_externo', 'tipo', 'serie', 'numero', 'xml_conteudo').order_by('created_at', 'id')
    count = missing = 0
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for document in documents.iterator(chunk_size=100):
            if not document.xml_conteudo:
                missing += 1
                continue
            name = re.sub(r'[^A-Za-z0-9_-]', '', f'{document.tipo}-{document.serie}-{document.numero}')
            # Data fixa torna o mesmo pacote idêntico em uma tentativa de reenvio.
            entry = zipfile.ZipInfo(f'notas/{name}-{document.id_externo}.xml', (1980, 1, 1, 0, 0, 0))
            archive.writestr(entry, bytes(document.xml_conteudo), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
            count += 1
            if output.tell() > MAX_ZIP_BYTES:
                raise FiscalValidationError('O ZIP excede 20 MB. Selecione um período menor para enviar.')
    if missing:
        raise FiscalError(f'Há {missing} nota(s) do período sem XML disponível. Regularize esses documentos antes do envio.', http_status=409)
    if not count:
        raise FiscalValidationError('Nenhuma NF-e ou NFC-e autorizada ou cancelada com XML foi encontrada no período e ambiente selecionados.')
    content = output.getvalue()
    if len(content) > MAX_ZIP_BYTES:
        raise FiscalValidationError('O ZIP excede 20 MB. Selecione um período menor para enviar.')
    return content, count


def enviar_xmls_contador(*, data_inicio, data_fim, email='', usuario=None):
    config = ConfiguracaoFiscal.atual()
    recipient = (email or config.email_contador).strip()
    try:
        validate_email(recipient)
        validate_email(config.email_remetente)
    except ValidationError:
        raise FiscalValidationError('Informe um e-mail válido para o contador e um remetente válido na configuração fiscal.')
    if not settings.RESEND_API_KEY:
        raise FiscalConfigurationError('O envio por e-mail ainda não foi configurado no servidor (Resend).')
    content, count = compactar_xmls(config, data_inicio, data_fim)
    filename = f'xmls-fiscais-{data_inicio.isoformat()}-a-{data_fim.isoformat()}-{config.ambiente}.zip'
    company = (config.nome_fantasia or config.razao_social or 'Bella Fornada').replace('\r', ' ').replace('\n', ' ')
    period = f'{data_inicio:%d/%m/%Y} a {data_fim:%d/%m/%Y}'
    payload = {
        'from': formataddr((company, config.email_remetente)),
        'to': [recipient],
        'subject': f'XMLs fiscais - {company} - {period}',
        'text': f'Seguem em anexo {count} XML(s) de NF-e e NFC-e autorizadas ou canceladas de {company}.\nPeríodo de emissão: {period}.\nAmbiente: {config.ambiente}.\nOs arquivos estão compactados em ZIP.',
        'attachments': [{'filename': filename, 'content': base64.b64encode(content).decode('ascii'), 'content_type': 'application/zip'}],
    }
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    try:
        response = requests.post(
            'https://api.resend.com/emails',
            headers={'Authorization': f'Bearer {settings.RESEND_API_KEY}', 'Idempotency-Key': f'fiscal-xml/{fingerprint}', 'Content-Type': 'application/json'},
            json=payload, timeout=(5, 30),
        )
    except requests.Timeout:
        raise FiscalError('O serviço demorou para confirmar o envio. Tente novamente; o mesmo pacote não será enviado em duplicidade.', http_status=504)
    except requests.RequestException:
        raise FiscalError('Não foi possível conectar ao serviço de e-mail. Tente novamente.', http_status=503)
    if response.status_code in (401, 403):
        raise FiscalConfigurationError('Confira o token do Resend e a autorização do domínio do remetente.')
    if response.status_code == 429:
        raise FiscalError('O serviço de e-mail atingiu um limite temporário. Aguarde e tente novamente.', http_status=503)
    if not response.ok:
        raise FiscalError('O Resend não aceitou o envio. Confira o remetente e tente novamente.', http_status=502)
    try:
        message_id = response.json()['id']
        if not isinstance(message_id, str) or not message_id:
            raise ValueError('Resposta sem identificador')
    except (ValueError, KeyError, TypeError):
        raise FiscalError('O serviço retornou uma confirmação inválida. Tente novamente.', http_status=502)
    logger.info('Envio de XMLs aceito pelo Resend: usuario=%s quantidade=%s id=%s', getattr(usuario, 'pk', None), count, message_id)
    return {'email': recipient, 'quantidade': count, 'arquivo': filename, 'resend_id': message_id, 'ambiente': config.ambiente}
