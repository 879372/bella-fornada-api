from decimal import Decimal

import pytest

from apps.fiscal.models import ConfiguracaoFiscal, DocumentoFiscal
from apps.vendas.tests.factories import UserFactory, VendaFactory, VendaItemFactory


def document(sale, status, environment='producao', suffix=''):
    return DocumentoFiscal.objects.create(
        venda=sale, tipo='NFCE', status=status, ambiente=environment,
        valor_total=Decimal(str(sale.total)) - Decimal(str(sale.desconto)),
        referencia=f'{sale.pk}:{status}:{environment}:{suffix}',
    )


@pytest.mark.django_db
def test_fiscal_totals_scope_environment_no_duplicate_pending_and_net_values(auth_client):
    config = ConfiguracaoFiscal.atual()
    config.ambiente = 'producao'
    config.save()
    authorized = VendaFactory(status='FINALIZADA', total='100.00', desconto='10.00')
    document(authorized, 'AUTORIZADA')
    authorized.total = Decimal('999.00')
    authorized.save(update_fields=['total'])  # O total fiscal preserva o valor emitido.
    pending = VendaFactory(status='FINALIZADA', total='40.00', desconto='5.00')
    VendaItemFactory(venda=pending, quantidade=1, preco_unitario='40.00')
    document(pending, 'REJEITADA')
    document(pending, 'ERRO')
    without_note = VendaFactory(status='FINALIZADA', total='20.00')
    VendaItemFactory(venda=without_note, quantidade=1, preco_unitario='20.00')
    document(without_note, 'AUTORIZADA', environment='homologacao')
    canceled = VendaFactory(status='FINALIZADA', total='30.00')
    VendaItemFactory(venda=canceled, quantidade=1, preco_unitario='30.00')
    document(canceled, 'CANCELADA')
    VendaFactory(status='FINALIZADA', total='500.00')  # Sem itens: não pode emitir.
    VendaFactory(status='CANCELADA', total='800.00')

    response = auth_client.get('/api/fiscal/documentos/totalizadores/')
    assert response.status_code == 200
    assert response.data['ambiente'] == 'producao'
    assert response.data['transmitidas']['quantidade'] == 1
    assert Decimal(response.data['transmitidas']['valor']) == Decimal('90.00')
    assert response.data['pendentes']['quantidade'] == 2
    assert Decimal(response.data['pendentes']['valor']) == Decimal('55.00')


@pytest.mark.django_db
def test_fiscal_totals_respect_operator_and_eligible_sale_filter(api_client, auth_client):
    user = UserFactory()
    own = VendaFactory(status='FINALIZADA', total='12.00', sessao__operador=user)
    VendaItemFactory(venda=own, quantidade=1, preco_unitario='12.00')
    other = VendaFactory(status='FINALIZADA', total='25.00')
    VendaItemFactory(venda=other, quantidade=1, preco_unitario='25.00')
    eligible = auth_client.get('/api/fiscal/documentos/vendas-elegiveis/', {'venda': own.pk})
    assert eligible.data['count'] == 1
    assert eligible.data['results'][0]['id'] == own.pk

    api_client.force_authenticate(user=user)
    response = api_client.get('/api/fiscal/documentos/totalizadores/')
    assert response.status_code == 200
    assert response.data['pendentes']['quantidade'] == 1
    assert Decimal(response.data['pendentes']['valor']) == Decimal('12.00')
    eligible = api_client.get('/api/fiscal/documentos/vendas-elegiveis/', {'venda': other.pk})
    assert eligible.data['count'] == 0
