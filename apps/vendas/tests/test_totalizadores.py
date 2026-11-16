from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.vendas.models import Venda
from apps.vendas.tests.factories import VendaFactory


@pytest.mark.django_db
def test_totals_cover_all_pages_apply_filters_and_discounts(auth_client):
    for _ in range(51):
        VendaFactory(status='FINALIZADA', total='10.00', desconto='1.00')
    canceled = VendaFactory(status='CANCELADA', total='20.00', desconto='2.00')
    VendaFactory(status='EM_ABERTO', total='5.00')

    response = auth_client.get('/api/vendas/totalizadores/')
    assert response.status_code == 200
    assert response.data['total']['quantidade'] == 53
    assert Decimal(response.data['finalizadas']['valor']) == Decimal('459.00')
    assert response.data['finalizadas']['quantidade'] == 51
    assert Decimal(response.data['canceladas']['valor']) == Decimal('18.00')

    filtered = auth_client.get('/api/vendas/totalizadores/', {'q': f'#{canceled.pk}', 'status': 'CANCELADA'})
    assert filtered.data['total']['quantidade'] == 1
    assert filtered.data['finalizadas']['quantidade'] == 0
    assert Decimal(filtered.data['total']['valor']) == Decimal('18.00')
    listed = auth_client.get('/api/vendas/', {'q': f'#{canceled.pk}'})
    assert listed.data['count'] == 1
    assert listed.data['results'][0]['id'] == canceled.pk

    Venda.objects.filter(pk=canceled.pk).update(data=timezone.now() - timezone.timedelta(days=10))
    dated = auth_client.get('/api/vendas/totalizadores/', {'data_inicio': timezone.localdate().isoformat()})
    assert dated.data['canceladas']['quantidade'] == 0


@pytest.mark.django_db
def test_empty_totals_and_authentication(auth_client):
    assert APIClient().get('/api/vendas/totalizadores/').status_code == 401
    response = auth_client.get('/api/vendas/totalizadores/')
    assert response.data['total'] == {'quantidade': 0, 'valor': '0.00'}
